````markdown
# whichlas

A command-line Python tool to tell you exactly which `.las` tiles you need to download to cover a given geographic bounding box. It reads a shapefile index of LIDAR tiles, reprojects your query from EPSG:4326 to the index’s CRS, computes coverage stats, and writes out the list of needed tile names.

If there's a shortfall in coverage, it'll save a high-res TIFF, `coverage_map.tiff` in the current directory to illustrate the coverage shortfall.

## Installation

Assuming you have Miniconda (or Anaconda) installed:

```bash
# 1. Clone the repo
git clone https://github.com/davidemerson/whichlas.git
cd whichlas

# 2. Create & activate a dedicated environment
conda create -n whichlas python=3.9 -y
conda activate whichlas

# 3. Install dependencies
pip install fiona shapely pyproj tabulate colorama geopandas matplotlib contextily
````

> **Note:** You need the four components of the shapefile index in the same folder:
>
> * `NYC2021_LAS_Index.shp`
> * `NYC2021_LAS_Index.dbf`
> * `NYC2021_LAS_Index.shx`
> * `NYC2021_LAS_Index.prj`

You can use the sample data shipped in `sample_data/` to test.

## Usage

```bash
python whichlas.py \
  --shp /path/to/NYC2021_LAS_Index.shp \
  --minx <lon_min> \
  --miny <lat_min> \
  --maxx <lon_max> \
  --maxy <lat_max> \
  [--buffer <deg_buffer>] \
  [--out <output_file>]
```

* `--shp`
  Path to the `.shp` index (with its `.dbf`, `.shx`, and `.prj` alongside).

* `--minx`, `--miny`, `--maxx`, `--maxy`
  Longitude/latitude corners of your bounding box (in EPSG:4326).

* `--buffer` *(optional, default=0.0)*
  Expand the bounding box by this amount in degrees (e.g. `0.001` ≈100 m).

* `--out` *(optional, default=`tiles.txt`)*
  Filename to write one `.las` tile name per line.

### Example

Suppose you want all `.las` tiles covering NYC Mesh as of 2025-06-24, with a small 100 m buffer:

```bash
python whichlas.py --shp sample_data/NYC2021_LAS_Index.shp --minx -74.067343 --miny 40.702124 --maxx -73.923577 --maxy 40.823916 --buffer 0.001 --out lasneeded.txt
```

This will:

1. Print a compact summary table showing:

   * Index CRS (EPSG code & name)
   * Total tiles in the index
   * Number of tiles **needed** and % of index used
   * Bounding-box area vs. total tile coverage area (km² & mi²)
   * Coverage % and overrun/underrun %
   * A red warning if coverage < 100%

2. List the needed tile names in neat columns.

3. Write the tile list to `lasneeded.txt`.

## What’s under the hood?

1. **Auto-detects** the shapefile’s file-name attribute (any property starting with “file…”).
2. **Reprojects** your lon/lat query from EPSG:4326 into the shapefile’s CRS via `pyproj` & `shapely`.
3. **Computes**:

   * Bounding-box area
   * Union of all intersecting tile polygons
   * Area overrun or underrun
   * % of total index tiles used
4. **Formats** output with `tabulate` and colorizes warnings with `colorama`.

## Troubleshooting

* **“Shapefile not found”**
  Ensure your `--shp` path is correct and that `.dbf`/`.shx`/`.prj` live alongside.

* **Coverage < 100%**
  Tiles don’t fully cover your box. You may need to check:

  * Buffer size
  * Correct CRS / coordinate swap (lon vs. lat)

* **Dependencies fail**
  Make sure you’re in the `whichlas` Conda env and rerun:

  ```bash
  pip install fiona shapely pyproj tabulate colorama
  ```