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
from pathlib import Path

import fiona
import pandas as pd
from shapely.geometry import box, shape, Point, LineString
from shapely.ops import transform, unary_union
from pyproj import Transformer, CRS
from tabulate import tabulate
from colorama import init, Fore, Style

# unit conversions
FT2_TO_M2 = 0.09290304
FT2_TO_MI2 = 1 / (5280 ** 2)


def parse_args():
    p = argparse.ArgumentParser(
        description="Which LAS tiles cover a bbox or CSV of points+path?"
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
    return p.parse_args()


def columns(lst, cols=4, width=16):
    lines = []
    for i in range(0, len(lst), cols):
        lines.append("".join(f"{s:<{width}}" for s in lst[i : i + cols]))
    return "\n".join(lines)


def build_query_geometry(args):
    if args.csv:
        df = pd.read_csv(args.csv)
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
        pts = [Point(x, y) for x, y in zip(df[xcol], df[ycol])]
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
        geom = box(args.minx, args.miny, args.maxx, args.maxy).buffer(args.buffer)
        return geom, True, []


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

    with fiona.open(str(shp)) as src:
        total_tiles = len(src)
        pj = CRS(src.crs)
        auth = pj.to_authority()
        crs_label = f"{auth[0]}:{auth[1]} — {pj.name}" if auth else pj.name

        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
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

    # always generate map
    try:
        import geopandas as gpd
        import matplotlib.pyplot as plt
        import contextily as ctx

        gdf_all = gpd.read_file(str(shp))
        gdf_sel = gdf_all[gdf_all[fld].isin(set(hits))]
        gdf_query = gpd.GeoDataFrame(
            {"geometry": [query_geom]}, crs=src.crs
        )
        # also GeoDataFrame of the raw points for plotting
        gdf_pts = gpd.GeoDataFrame(
            {"geometry": point_list}, crs="EPSG:4326"
        )
        
        # reproject
        for gdf in (gdf_all, gdf_sel, gdf_query):
            gdf.to_crs(epsg=3857, inplace=True)
        if not gdf_pts.empty:
            gdf_pts = gdf_pts.to_crs(epsg=3857)

        fig, ax = plt.subplots(1, 1, figsize=(12, 12))
        gdf_all.boundary.plot(ax=ax, color="lightgray", linewidth=0.5)
        gdf_sel.plot(ax=ax, color="blue", alpha=0.5, edgecolor="navy")
        gdf_query.boundary.plot(ax=ax, color="red", linewidth=2)
        if not gdf_pts.empty:
            gdf_pts.plot(ax=ax, color="yellow", marker="o", markersize=50, edgecolor="black")

        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        ax.set_title("Coverage map")
        ax.set_axis_off()

        outmap = Path("coverage_map.tiff")
        fig.savefig(str(outmap), dpi=300, bbox_inches="tight")
        print(Fore.GREEN + f"Wrote coverage map to {outmap}")
        plt.close(fig)

    except Exception as e:
        print(Fore.YELLOW + "Warning: map generation failed:", e)

    # list and write tiles
    uniq = sorted(set(hits))
    print("\n" + Style.BRIGHT + "Tiles:")
    print(columns(uniq))

    with open(args.out, "w") as f:
        f.write("\n".join(uniq))
    print(
        Fore.GREEN
        + f"\nList written to {args.out} ({used}/{total_tiles} tiles, {pct_used:.1f}% of index)"
    )


if __name__ == "__main__":
    main()
