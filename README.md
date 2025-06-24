# whichlas
A script which tells you which .las file you need to get all data inside a geographic box.

`whichlas.py` is a simple command-line tool that reads a shapefile index of LIDAR `.las` tiles and reports which tile files intersect (or slightly exceed) any user-specified bounding box. This helps you determine exactly which `.las` files to download for full coverage of your area of interest.

I made this when I was working on jpmapper-lidar because the ftp server hosting the (many) `.las` files for the NYC 2021 LIDAR dataset was so slow, and I didn't need all the files to represent a small portion of the NYC metro area.

## Prerequisites

- **Python 3.7+**
- **Fiona** (for reading shapefiles):
  ```
  pip install fiona
````
- **Shapely** (for geometric operations):
  ```
  pip install shapely
  ```

Make sure the following shapefile components are present in the same directory:
* `NYC2021_LAS_Index.shp`
* `NYC2021_LAS_Index.dbf`
* `NYC2021_LAS_Index.shx`
* `NYC2021_LAS_Index.prj`

You'll find all these in the sample_data here in this repo, so you can use those as a test.

## Usage

```
python find_las_tiles.py \
  --shp /path/to/NYC2021_LAS_Index.shp \
  --minx <longitude_min> \
  --miny <latitude_min> \
  --maxx <longitude_max> \
  --maxy <latitude_max> \
  [--buffer <buffer_distance>]
```

* `--shp`
  Path to the shapefile index (including `.shp`, `.dbf`, `.shx` together).
* `--minx`, `--miny`, `--maxx`, `--maxy`
  Coordinates defining your query bounding box (in the same CRS as the shapefile, e.g., longitude/latitude).
* `--buffer` *(optional)*
  Expand the query box by this amount (in the same units) to ensure you don’t miss edge tiles.

### Example

To find all tiles covering roughly downtown Manhattan (with a tiny 100 m buffer):

```bash
python find_las_tiles.py \
  --shp ~/data/NYC2021_LAS_Index.shp \
  --minx -74.02 --miny 40.70 \
  --maxx -73.95 --maxy 40.78 \
  --buffer 0.001
```

This will print a sorted list of the `.las` filenames you need to download.

## Notes

* The script auto-detects which attribute in the shapefile holds the file path (looks for the first property starting with “file…”).
* If your index uses a different field name, you can adjust the code in the `field = next(…)` line to match it explicitly.
* Ensure your query coordinates use the same CRS as the shapefile (e.g., EPSG:4326 for lon/lat).