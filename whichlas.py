#!/usr/bin/env python3
"""
whichlas.py

Find which LAS tiles cover (or overlap) a given bounding box,
reading from a .shp shapefile, reprojecting from EPSG:4326,
reporting coverage with a compact, colorized summary, and
if coverage is partial, generating a coverage_map.tiff that
plots all index tiles, selected tiles, and the query bbox
over an OpenStreetMap basemap layer for context.
"""

import argparse
import sys
from pathlib import Path

import fiona
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer, CRS
from tabulate import tabulate
from colorama import init, Fore, Style

# unit conversions
FT2_TO_M2 = 0.09290304
FT2_TO_MI2 = 1 / (5280 ** 2)


def parse_args():
    p = argparse.ArgumentParser(description="Which LAS tiles for my bbox?")
    p.add_argument("--shp",   required=True, help="Index .shp (with .dbf/.shx/.prj)")
    p.add_argument("--minx",  type=float, required=True, help="Lon min")
    p.add_argument("--miny",  type=float, required=True, help="Lat min")
    p.add_argument("--maxx",  type=float, required=True, help="Lon max")
    p.add_argument("--maxy",  type=float, required=True, help="Lat max")
    p.add_argument("--buffer", type=float, default=0.0, help="BBox buffer (deg)")
    p.add_argument("--out",   default="tiles.txt", help="Write filenames here")
    return p.parse_args()


def columns(lst, cols=4, width=16):
    lines = []
    for i in range(0, len(lst), cols):
        lines.append("".join(f"{s:<{width}}" for s in lst[i:i+cols]))
    return "\n".join(lines)


def main():
    init(autoreset=True)
    args = parse_args()
    shp = Path(args.shp).expanduser().resolve()
    if not shp.exists():
        print(Fore.RED + "Shapefile not found:", shp)
        sys.exit(1)

    # Build the input bbox in lon/lat
    bbox = box(args.minx, args.miny, args.maxx, args.maxy).buffer(args.buffer)

    with fiona.open(str(shp)) as src:
        total_tiles = len(src)

        pj = CRS(src.crs)
        epsg = pj.to_authority()
        crs_label = f"{epsg[0]}:{epsg[1]} — {pj.name}" if epsg else pj.name

        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        qry = transform(transformer.transform, bbox)

        fld = next((f for f in src.schema["properties"] if f.lower().startswith("file")), None)
        if not fld:
            print(Fore.RED + "No file-name field in schema")
            sys.exit(1)

        hits, geoms = [], []
        for feat in src:
            g = shape(feat["geometry"])
            if g.intersects(qry):
                hits.append(feat["properties"][fld])
                geoms.append(g)

    if not hits:
        print(Fore.RED + "No tiles found.")
        sys.exit(0)

    # Area calculations
    area_ft2 = qry.area
    km2_bbox = area_ft2 * FT2_TO_M2 / 1e6
    mi2_bbox = area_ft2 * FT2_TO_MI2

    uni = unary_union(geoms)
    area2_ft2 = uni.area
    km2_tiles = area2_ft2 * FT2_TO_M2 / 1e6
    mi2_tiles = area2_ft2 * FT2_TO_MI2

    coverage_pct = area2_ft2 / area_ft2 * 100
    overrun_pct = coverage_pct - 100

    used_tiles = len(set(hits))
    pct_tiles = used_tiles / total_tiles * 100

    # Summary table
    rows = [
        ["CRS",                  crs_label],
        ["Total tiles in index", str(total_tiles)],
        ["Tiles needed",          str(used_tiles)],
        ["% of index used",       f"{pct_tiles:.1f}%"],
        ["BBox km²",             f"{km2_bbox:.2f}"],
        ["BBox mi²",             f"{mi2_bbox:.2f}"],
        ["Tiles km²",            f"{km2_tiles:.2f}"],
        ["Tiles mi²",            f"{mi2_tiles:.2f}"],
        ["Coverage",             f"{coverage_pct:.1f}%"],
        ["Overrun",              f"{overrun_pct:.1f}%"],
    ]
    if coverage_pct < 100:
        rows.append([Fore.RED + "WARNING", Fore.RED + "Partial coverage!"])

    print(Style.BRIGHT + tabulate(rows, tablefmt="plain"))

    # Generate coverage map if partial
    if coverage_pct < 100:
        try:
            import geopandas as gpd
            import matplotlib.pyplot as plt
            import contextily as ctx

            # Load index and selected tiles
            gdf_all = gpd.read_file(str(shp))
            gdf_sel = gdf_all[gdf_all[fld].isin(set(hits))]

            # Query bbox
            gdf_box = gpd.GeoDataFrame({"geometry": [qry]}, crs=src.crs)

            # Reproject to Web Mercator
            gdf_all = gdf_all.to_crs(epsg=3857)
            gdf_sel = gdf_sel.to_crs(epsg=3857)
            gdf_box = gdf_box.to_crs(epsg=3857)

            # Plot
            fig, ax = plt.subplots(1, 1, figsize=(12, 12))
            gdf_all.boundary.plot(ax=ax, color="lightgray", linewidth=0.5)
            gdf_sel.plot(ax=ax, color="blue", alpha=0.5, edgecolor="navy")
            gdf_box.boundary.plot(ax=ax, color="red", linewidth=2)

            # Add OSM basemap
            ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)

            ax.set_title("Tile coverage vs. Query bounding box")
            ax.set_axis_off()

            outmap = Path("coverage_map.tiff")
            fig.savefig(str(outmap), dpi=300, bbox_inches="tight")
            print(Fore.GREEN + f"Wrote coverage map to {outmap}")
            plt.close(fig)

        except Exception as e:
            print(Fore.YELLOW + "Warning: failed to write coverage_map.tiff:", e)

    # Print tile list
    uniq = sorted(set(hits))
    print("\n" + Style.BRIGHT + "Tiles:")
    print(columns(uniq))

    # Write to file
    with open(args.out, "w") as f:
        f.write("\n".join(uniq))
    print(Fore.GREEN + f"\nList written to {args.out} ({used_tiles}/{total_tiles} tiles, {pct_tiles:.1f}% of index)")


if __name__ == "__main__":
    main()
