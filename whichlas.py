#!/usr/bin/env python3
"""
whichlas.py

Find which LAS tiles cover (or overlap) a given bounding box,
reading directly from a .shp shapefile.

Dependencies:
    pip install fiona shapely

Usage:
    python whichlas.py \
        --shp /path/to/NYC2021_LAS_Index.shp \
        --minx <lon_min> --miny <lat_min> \
        --maxx <lon_max> --maxy <lat_max> \
        [--buffer <buffer_distance>]
"""

import argparse
import fiona
from shapely.geometry import box, shape

def parse_args():
    parser = argparse.ArgumentParser(
        description="Find LAS tiles overlapping a bounding box."
    )
    parser.add_argument(
        "--shp", required=True,
        help="Path to the .shp index file (plus accompanying .dbf, .shx, etc.)"
    )
    parser.add_argument(
        "--minx", type=float, required=True, help="Query bbox minimum X (lon)"
    )
    parser.add_argument(
        "--miny", type=float, required=True, help="Query bbox minimum Y (lat)"
    )
    parser.add_argument(
        "--maxx", type=float, required=True, help="Query bbox maximum X (lon)"
    )
    parser.add_argument(
        "--maxy", type=float, required=True, help="Query bbox maximum Y (lat)"
    )
    parser.add_argument(
        "--buffer", type=float, default=0.0,
        help="Optional buffer (in same units) to expand the query box"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    # Create the query polygon, with optional buffer
    query_poly = box(args.minx, args.miny, args.maxx, args.maxy).buffer(args.buffer)

    tile_files = []
    with fiona.open(args.shp) as src:
        # Auto-detect the file path field (e.g. 'location' or 'file_name')
        field = next(
            (f for f in src.schema["properties"] if f.lower().startswith("file")),
            None
        )
        if field is None:
            raise RuntimeError("Couldn't find a file-name field in the shapefile schema.")

        for feature in src:
            geom = shape(feature["geometry"])
            if geom.intersects(query_poly):
                tile_files.append(feature["properties"][field])

    if tile_files:
        print("Tiles covering your area:")
        for fpath in sorted(set(tile_files)):
            print(f"  - {fpath}")
    else:
        print("No tiles overlap the specified bounding box.")

if __name__ == "__main__":
    main()
