#!/usr/bin/env python3
"""
whichlas.py

Find which LAS tiles cover either:
  • a bounding box (--minx/--miny/--maxx/--maxy), or
  • a set of points & connecting path (--csv <file.csv>)

Reads a .shp index of tiles, reprojects from EPSG:4326,
reports coverage stats, lists needed tiles, and always
generates a coverage_map.tiff with a contextual basemap.
In CSV mode, takes the convex hull of your points+path to
fill any interior gaps, and plots the points as dots on the map.
"""

import argparse
import sys
import json
from pathlib import Path
from typing import List, Tuple, Optional, Union

import fiona
import pandas as pd
from shapely.geometry import box, shape, Point, LineString, Polygon
from shapely.ops import transform, unary_union
from pyproj import Transformer, CRS
from tabulate import tabulate
from colorama import init, Fore, Style

# Optional imports for mapping (graceful fallback)
try:
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import contextily as ctx
    HAS_MAPPING = True
except ImportError:
    HAS_MAPPING = False

# unit conversions
FT2_TO_M2 = 0.09290304
FT2_TO_MI2 = 1 / (5280 ** 2)


def parse_args():
    p = argparse.ArgumentParser(
        description="Which LAS tiles cover a bbox or CSV of points+path?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bounding box mode
  %(prog)s --shp tiles.shp --minx -74.1 --miny 40.7 --maxx -73.9 --maxy 40.8

  # CSV points mode  
  %(prog)s --shp tiles.shp --csv points.csv

  # With custom output formats
  %(prog)s --shp tiles.shp --csv points.csv --format json --out tiles.json
        """
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--csv", help="Path to CSV with point coordinates (e.g. lon,lat or x,y)"
    )
    grp.add_argument(
        "--minx", type=float, help="Lon min (for bbox search once you specify all four)"
    )
    p.add_argument("--miny", type=float, help="Lat min")
    p.add_argument("--maxx", type=float, help="Lon max")
    p.add_argument("--maxy", type=float, help="Lat max")
    p.add_argument(
        "--buffer", type=float, default=0.0, help="Buffer in degrees (bbox only)"
    )
    p.add_argument("--csvx", help="Column name for point X (lon) if auto-detect fails")
    p.add_argument("--csvy", help="Column name for point Y (lat) if auto-detect fails")
    p.add_argument("--shp", required=True, help="Index .shp (with .dbf/.shx/.prj)")
    p.add_argument("--out", default="tiles.txt", help="Write filenames here")
    p.add_argument(
        "--format", 
        choices=["txt", "json", "csv"], 
        default="txt",
        help="Output format (default: txt)"
    )
    p.add_argument(
        "--input-crs",
        default="EPSG:4326", 
        help="Input coordinate system (default: EPSG:4326)"
    )
    p.add_argument(
        "--no-map", 
        action="store_true", 
        help="Skip map generation"
    )
    p.add_argument(
        "--preview", 
        action="store_true", 
        help="Show query geometry info without processing tiles"
    )
    return p.parse_args()


def columns(lst, cols=4, width=16):
    lines = []
    for i in range(0, len(lst), cols):
        lines.append("".join(f"{s:<{width}}" for s in lst[i : i + cols]))
    return "\n".join(lines)


def validate_coordinates(x, y, crs="EPSG:4326"):
    """Validate that coordinates are reasonable for the given CRS."""
    if crs.upper() == "EPSG:4326":
        # WGS84 bounds
        if not (-180 <= x <= 180):
            raise ValueError(f"Longitude {x} out of bounds [-180, 180]")
        if not (-90 <= y <= 90):
            raise ValueError(f"Latitude {y} out of bounds [-90, 90]")
    return True


def build_query_geometry(args):
    """Build the query geometry from either CSV or bbox arguments."""
    if args.csv:
        csv_path = Path(args.csv).expanduser().resolve()
        if not csv_path.exists():
            raise ValueError(f"CSV file not found: {csv_path}")
            
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise ValueError(f"Error reading CSV: {e}")
            
        if df.empty:
            raise ValueError("CSV file is empty")
            
        # auto-detect X/Y columns
        xcol = args.csvx or next(
            (c for c in df.columns if c.lower() in ("lon", "longitude", "x", "lng")), None
        )
        ycol = args.csvy or next(
            (c for c in df.columns if c.lower() in ("lat", "latitude", "y")), None
        )
        if not xcol or not ycol:
            raise ValueError(
                f"Couldn't find lon/lat columns in CSV. "
                f"Please specify with --csvx and --csvy. Available: {', '.join(df.columns)}"
            )
            
        # Validate coordinates
        for idx, (x, y) in enumerate(zip(df[xcol], df[ycol])):
            if pd.isna(x) or pd.isna(y):
                raise ValueError(f"Missing coordinates at row {idx + 1}")
            try:
                validate_coordinates(float(x), float(y), args.input_crs)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid coordinates at row {idx + 1}: {e}")
                
        pts = [Point(x, y) for x, y in zip(df[xcol], df[ycol])]
        
        if len(pts) < 2:
            # Single point - just buffer it slightly
            geom = pts[0].buffer(0.001)  # ~100m buffer
        else:
            # Multiple points - create path and convex hull
            path = LineString([(p.x, p.y) for p in pts])
            union = unary_union(pts + [path])
            # take convex hull to fill any interior gaps
            geom = union.convex_hull
            
        return geom, False, pts
    else:
        if None in (args.miny, args.maxx, args.maxy):
            raise ValueError(
                "Must specify --minx/--miny/--maxx/--maxy for bbox mode"
            )
            
        # Validate bbox coordinates
        validate_coordinates(args.minx, args.miny, args.input_crs)
        validate_coordinates(args.maxx, args.maxy, args.input_crs)
        
        if args.minx >= args.maxx:
            raise ValueError("minx must be less than maxx")
        if args.miny >= args.maxy:
            raise ValueError("miny must be less than maxy")
            
        geom = box(args.minx, args.miny, args.maxx, args.maxy)
        if args.buffer > 0:
            geom = geom.buffer(args.buffer)
        return geom, True, []


def write_output(tiles: List[str], filepath: str, format_type: str, **metadata):
    """Write tiles list in the specified format."""
    if format_type == "txt":
        with open(filepath, "w") as f:
            f.write("\n".join(tiles))
    elif format_type == "json":
        data = {
            "tiles": tiles,
            "count": len(tiles),
            **metadata
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    elif format_type == "csv":
        df = pd.DataFrame({"filename": tiles})
        df.to_csv(filepath, index=False)


def generate_coverage_map(gdf_all, gdf_sel, gdf_query, gdf_pts, output_path="coverage_map.tiff"):
    """Generate and save the coverage map."""
    if not HAS_MAPPING:
        print(Fore.YELLOW + "Warning: Mapping libraries not available. Install with:")
        print("  pip install geopandas matplotlib contextily")
        return False
        
    try:
        # Make copies to avoid modifying original dataframes
        gdf_all_map = gdf_all.copy()
        gdf_sel_map = gdf_sel.copy()
        gdf_query_map = gdf_query.copy()
        
        # reproject to Web Mercator for mapping
        gdf_all_map = gdf_all_map.to_crs(epsg=3857)
        gdf_sel_map = gdf_sel_map.to_crs(epsg=3857)
        gdf_query_map = gdf_query_map.to_crs(epsg=3857)
        
        if not gdf_pts.empty:
            gdf_pts_map = gdf_pts.to_crs(epsg=3857)
        else:
            gdf_pts_map = gdf_pts

        fig, ax = plt.subplots(1, 1, figsize=(12, 12))
        
        # Plot layers
        gdf_all_map.boundary.plot(ax=ax, color="lightgray", linewidth=0.5, alpha=0.7)
        gdf_sel_map.plot(ax=ax, color="blue", alpha=0.6, edgecolor="navy", linewidth=1)
        gdf_query_map.boundary.plot(ax=ax, color="red", linewidth=2.5)
        
        if not gdf_pts_map.empty:
            gdf_pts_map.plot(ax=ax, color="yellow", marker="o", markersize=60, 
                           edgecolor="black", linewidth=1.5)

        # Add basemap
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, alpha=0.8)
        
        # Styling
        ax.set_title("LAS Tile Coverage Map", fontsize=16, fontweight='bold', pad=20)
        ax.set_axis_off()

        # Save with high quality
        fig.savefig(str(output_path), dpi=300, bbox_inches="tight", 
                   facecolor='white', edgecolor='none')
        print(Fore.GREEN + f"Coverage map saved: {output_path}")
        plt.close(fig)
        return True
        
    except Exception as e:
        print(Fore.YELLOW + f"Warning: Map generation failed: {e}")
        return False


def main():
    init(autoreset=True)
    args = parse_args()
    shp = Path(args.shp).expanduser().resolve()
    if not shp.exists():
        print(Fore.RED + "Shapefile not found:", shp)
        sys.exit(1)

    try:
        query_geom_ll, is_bbox, point_list = build_query_geometry(args)
    except Exception as e:
        print(Fore.RED + str(e))
        sys.exit(1)

    # Preview mode - show geometry info and exit
    if args.preview:
        print(Style.BRIGHT + "Query Geometry Preview:")
        if is_bbox:
            bounds = query_geom_ll.bounds
            print(f"  Type: Bounding Box")
            print(f"  Bounds: {bounds}")
            print(f"  Buffer: {args.buffer} degrees")
        else:
            print(f"  Type: CSV Points/Path")
            print(f"  Points: {len(point_list)}")
            print(f"  Geometry: {query_geom_ll.geom_type}")
            if hasattr(query_geom_ll, 'bounds'):
                print(f"  Bounds: {query_geom_ll.bounds}")
        print(f"  Input CRS: {args.input_crs}")
        return

    with fiona.open(str(shp)) as src:
        total_tiles = len(src)
        pj = CRS(src.crs)
        auth = pj.to_authority()
        crs_label = f"{auth[0]}:{auth[1]} — {pj.name}" if auth else pj.name

        transformer = Transformer.from_crs(args.input_crs, src.crs, always_xy=True)
        query_geom = transform(transformer.transform, query_geom_ll)

        fld = next(
            (f for f in src.schema["properties"] if f.lower().startswith("file")), None
        )
        if not fld:
            print(Fore.RED + "No file-name field in schema")
            sys.exit(1)

        hits, geoms = [], []
        for feat in src:
            g = shape(feat["geometry"])
            if g.intersects(query_geom):
                hits.append(feat["properties"][fld])
                geoms.append(g)

    if not hits:
        print(Fore.RED + "No tiles found.")
        sys.exit(0)

    # area metrics (feet²)
    area_ft2 = query_geom.area
    km2_q = area_ft2 * FT2_TO_M2 / 1e6
    mi2_q = area_ft2 * FT2_TO_MI2

    union_sel = unary_union(geoms)
    area2_ft2 = union_sel.area
    km2_t = area2_ft2 * FT2_TO_M2 / 1e6
    mi2_t = area2_ft2 * FT2_TO_MI2

    cov = area2_ft2 / area_ft2 * 100 if is_bbox else None
    over = cov - 100 if is_bbox else None

    used = len(set(hits))
    pct_used = used / total_tiles * 100

    # summary
    rows = [
        ["CRS", crs_label],
        ["Total tiles in index", str(total_tiles)],
        ["Tiles needed", str(used)],
        ["% of index used", f"{pct_used:.1f}%"],
    ]
    if is_bbox:
        rows += [
            ["BBox km²", f"{km2_q:.2f}"],
            ["BBox mi²", f"{mi2_q:.2f}"],
            ["Tiles km²", f"{km2_t:.2f}"],
            ["Tiles mi²", f"{mi2_t:.2f}"],
            ["Coverage", f"{cov:.1f}%"],
            ["Overrun", f"{over:.1f}%"],
        ]
        if cov < 100:
            rows.append([Fore.RED + "WARNING", Fore.RED + "Partial coverage!"])

    print(Style.BRIGHT + tabulate(rows, tablefmt="plain"))

    # Generate map (unless disabled)
    if not args.no_map and HAS_MAPPING:
        try:
            gdf_all = gpd.read_file(str(shp))
            # Use .copy() to avoid SettingWithCopyWarning
            gdf_sel = gdf_all[gdf_all[fld].isin(set(hits))].copy()
            gdf_query = gpd.GeoDataFrame(
                {"geometry": [query_geom]}, crs=pj
            )
            gdf_pts = gpd.GeoDataFrame(
                {"geometry": point_list}, crs=args.input_crs
            )
            
            generate_coverage_map(gdf_all, gdf_sel, gdf_query, gdf_pts)
            
        except Exception as e:
            print(Fore.YELLOW + f"Warning: Map generation failed: {e}")

    # list and write tiles
    uniq = sorted(set(hits))
    print("\n" + Style.BRIGHT + "Tiles:")
    print(columns(uniq))

    # Write output in requested format
    metadata = {
        "total_tiles_in_index": total_tiles,
        "tiles_used": used,
        "percent_index_used": round(pct_used, 1),
        "crs": crs_label,
        "query_type": "bbox" if is_bbox else "csv_points"
    }
    
    if is_bbox:
        metadata.update({
            "bbox_km2": round(km2_q, 2),
            "bbox_mi2": round(mi2_q, 2),
            "tiles_km2": round(km2_t, 2),
            "tiles_mi2": round(mi2_t, 2),
            "coverage_percent": round(cov, 1),
            "overrun_percent": round(over, 1)
        })

    write_output(uniq, args.out, args.format, **metadata)
    
    print(
        Fore.GREEN
        + f"\nOutput written to {args.out} ({used}/{total_tiles} tiles, {pct_used:.1f}% of index)"
    )


if __name__ == "__main__":
    main()
