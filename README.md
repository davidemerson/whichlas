# whichlas

A robust command-line Python tool to determine which LAS (LIDAR) tiles you need to cover either:
- **A bounding box** (specified with longitude/latitude coordinates)
- **A set of points and connecting path** (from a CSV file)

The tool reads a shapefile index of LIDAR tiles, reprojects your query geometry to match the index's coordinate system, computes detailed coverage statistics, and generates both a list of needed tiles and a visual coverage map.

**Key Features:**
- **Dual input modes**: Bounding box coordinates or CSV points/path analysis
- **Flexible coordinate systems**: Support for any input CRS (not just WGS84)
- **Multiple output formats**: Text, JSON, or CSV with rich metadata
- **Smart geometry handling**: Automatic convex hull generation for CSV mode
- **High-quality mapping**: Always generates coverage maps with contextual basemaps
- **Robust validation**: Comprehensive coordinate and file validation
- **Preview mode**: Inspect query geometry without processing
- **Graceful fallbacks**: Works even without optional mapping libraries
- **Production ready**: Extensive error handling and user-friendly messages

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
pip install fiona shapely pyproj tabulate colorama geopandas matplotlib contextily pandas
```

> **Note:** You need the four components of the shapefile index in the same folder:
>
> * `NYC2021_LAS_Index.shp`
> * `NYC2021_LAS_Index.dbf`
> * `NYC2021_LAS_Index.shx`
> * `NYC2021_LAS_Index.prj`

You can use the sample data shipped in `sample_data/` to test.

## Usage

The tool supports two main modes of operation with extensive customization options:

### Mode 1: Bounding Box Query

Specify a rectangular geographic area using longitude/latitude coordinates:

```bash
python whichlas.py \
  --shp /path/to/index.shp \
  --minx <lon_min> \
  --miny <lat_min> \
  --maxx <lon_max> \
  --maxy <lat_max> \
  [--buffer <degrees>] \
  [--input-crs <EPSG_CODE>] \
  [--format <txt|json|csv>] \
  [--out <output_file>]
```

### Mode 2: CSV Points and Path Analysis

Provide a CSV file with point coordinates. The tool will:
- Auto-detect coordinate columns (lon/lat, x/y, lng/latitude, etc.)
- Create a path connecting all points in order
- Generate a convex hull to cover the points, path, and any interior areas
- Plot the original points as yellow dots on the coverage map

```bash
python whichlas.py \
  --csv /path/to/points.csv \
  --shp /path/to/index.shp \
  [--csvx <x_column_name>] \
  [--csvy <y_column_name>] \
  [--input-crs <EPSG_CODE>] \
  [--format <txt|json|csv>] \
  [--out <output_file>]
```

### Preview Mode

Inspect your query geometry without processing the shapefile:

```bash
python whichlas.py \
  --preview \
  --csv points.csv \
  --shp index.shp
```

## Parameters

### Required Parameters

* `--shp` *(required)*
  Path to the shapefile index (`.shp` file with its `.dbf`, `.shx`, and `.prj` files alongside).

**Either bbox coordinates OR CSV file:**

### Bounding Box Mode
* `--minx`, `--miny`, `--maxx`, `--maxy` *(required for bbox mode)*
  Longitude/latitude corners of your bounding box (in the specified input CRS).

### CSV Points Mode
* `--csv` *(required for CSV mode)*
  Path to CSV file containing point coordinates.

### Optional Parameters

**Coordinate System & Validation:**
* `--input-crs` *(default: EPSG:4326)*
  Input coordinate reference system. Supports any EPSG code (e.g., "EPSG:3857", "EPSG:4326").

* `--buffer` *(default: 0.0)*
  Expand the bounding box by this amount in degrees (bbox mode only).

**CSV Configuration:**
* `--csvx`, `--csvy` *(optional)*
  Column names for X (longitude) and Y (latitude) coordinates if auto-detection fails.
  Auto-detection looks for: `lon`/`longitude`/`x`/`lng` and `lat`/`latitude`/`y`.

**Output Options:**
* `--out` *(default: tiles.txt)*
  Output filename for the tile list.

* `--format` *(default: txt)*
  Output format: `txt` (line-by-line), `json` (structured with metadata), or `csv` (tabular).

**Control Flags:**
* `--no-map`
  Skip map generation (useful for headless environments or when mapping libraries aren't available).

* `--preview`
  Show query geometry information and exit without processing tiles (useful for debugging).

## Output

The tool provides comprehensive output in multiple formats:

### 1. Terminal Summary
A detailed statistics table showing:
- **Index information**: CRS details and total tiles available
- **Usage statistics**: Number of tiles needed and percentage of index used
- **Area calculations** (bounding box mode only): Query area vs. tile coverage in km² and mi²
- **Coverage analysis** (bounding box mode only): Coverage percentage and overrun/underrun
- **Warnings**: Red alerts for incomplete coverage
- **Tile listing**: Organized in neat columns for easy reading

### 2. Coverage Map (`coverage_map.tiff`)
**Always generated** (unless `--no-map` is specified):
- **High-resolution TIFF** (300 DPI) with contextual OpenStreetMap basemap
- **All tiles** shown as light gray outlines with transparency
- **Selected tiles** highlighted in blue with navy borders
- **Query area** outlined in red (bold line)
- **Points** (CSV mode only) plotted as yellow dots with black borders
- **Professional styling** with clear title and clean presentation
- **Web Mercator projection** for optimal web map overlay compatibility

### 3. Output Files

#### Text Format (default)
```
tile001.las
tile002.las
tile003.las
```
Simple line-by-line format, perfect for shell scripts and basic processing.

#### JSON Format (`--format json`)
```json
{
  "tiles": ["tile001.las", "tile002.las", "tile003.las"],
  "count": 3,
  "total_tiles_in_index": 150,
  "tiles_used": 3,
  "percent_index_used": 2.0,
  "crs": "EPSG:2263 — NAD83 / New York Long Island",
  "query_type": "bbox",
  "bbox_km2": 1.25,
  "bbox_mi2": 0.48,
  "tiles_km2": 1.31,
  "tiles_mi2": 0.51,
  "coverage_percent": 105.2,
  "overrun_percent": 5.2
}
```
Rich metadata for integration with other tools and automated workflows.

#### CSV Format (`--format csv`)
```csv
filename
tile001.las
tile002.las
tile003.las
```
Tabular format ideal for importing into spreadsheets or databases.

## Examples

### Basic Bounding Box Query

Query tiles covering Manhattan with a 100m buffer:

```bash
python whichlas.py \
  --shp sample_data/NYC2021_LAS_Index.shp \
  --minx -74.067343 \
  --miny 40.702124 \
  --maxx -73.923577 \
  --maxy 40.823916 \
  --buffer 0.001 \
  --out manhattan_tiles.txt
```

### Advanced Bounding Box with JSON Output

Same area but with rich JSON metadata for integration:

```bash
python whichlas.py \
  --shp sample_data/NYC2021_LAS_Index.shp \
  --minx -74.067343 \
  --miny 40.702124 \
  --maxx -73.923577 \
  --maxy 40.823916 \
  --format json \
  --out manhattan_analysis.json
```

### CSV Survey Route Analysis

Find tiles covering a flight path or survey route:

```bash
python whichlas.py \
  --csv sample_data/points.csv \
  --shp sample_data/NYC2021_LAS_Index.shp \
  --format json \
  --out survey_route_tiles.json
```

### Working with Different Coordinate Systems

For data in NY State Plane (feet):

```bash
python whichlas.py \
  --csv ny_state_plane_points.csv \
  --input-crs EPSG:2263 \
  --shp sample_data/NYC2021_LAS_Index.shp \
  --csvx "easting" \
  --csvy "northing" \
  --format csv \
  --out tiles_analysis.csv
```

### Preview Mode for Debugging

Check your query geometry before processing:

```bash
python whichlas.py \
  --preview \
  --csv suspicious_coordinates.csv \
  --shp sample_data/NYC2021_LAS_Index.shp
```

### Headless/Server Usage

Skip map generation in automated environments:

```bash
python whichlas.py \
  --csv batch_points.csv \
  --shp large_index.shp \
  --no-map \
  --format json \
  --out batch_results.json
```

## Advanced Features

### Coordinate System Flexibility
- **Input CRS support**: Any EPSG coordinate system (WGS84, UTM, State Plane, etc.)
- **Automatic reprojection**: Seamlessly converts between input CRS and shapefile CRS
- **Coordinate validation**: Ensures coordinates are within reasonable bounds for the specified CRS

### Smart Geometry Processing
- **Single point handling**: Automatically buffers single points to create searchable areas
- **Convex hull generation**: Fills gaps between points and paths in CSV mode
- **Buffer options**: Expandable bounding boxes for safety margins

### Robust Error Handling
- **File validation**: Checks for shapefile completeness and CSV accessibility
- **Coordinate validation**: Validates lat/lon bounds and numeric formats
- **Schema detection**: Automatically finds filename fields in shapefiles
- **Graceful degradation**: Works even without optional mapping libraries

### Integration-Friendly
- **Multiple output formats**: Choose the format that works best with your workflow
- **Rich metadata**: JSON output includes comprehensive statistics for further analysis
- **Scriptable**: Perfect for batch processing and automated workflows
- **Standards compliant**: Uses standard geospatial libraries and formats

## Requirements

### Core Dependencies (Required)
```bash
pip install fiona shapely pyproj pandas tabulate colorama
```

### Optional Dependencies (For mapping)
```bash
pip install geopandas matplotlib contextily
```
*If mapping libraries aren't available, the tool will still work but skip map generation.*

### Shapefile Requirements

The tool requires a complete shapefile index with all four components:
- `*.shp` - Main shapefile with tile geometries
- `*.dbf` - Attribute database with tile filenames
- `*.shx` - Shape index for efficient reading
- `*.prj` - Projection information (CRS definition)

**Shapefile Schema Requirements:**
- Must contain a field with tile filenames (field name starting with "file")
- Geometries should represent the spatial extent of each tile
- CRS must be properly defined in the `.prj` file

## Troubleshooting

### Common Issues

**"No file-name field in schema"**
- The shapefile must have a field name starting with "file" (e.g., "filename", "file_name", "FILE_PATH")
- Check your shapefile's attribute table to ensure this field exists

**"Couldn't find lon/lat columns in CSV"**
- Use `--csvx` and `--csvy` to specify column names explicitly
- Check that column names don't have extra spaces or special characters
- Verify your CSV has headers

**"Longitude X out of bounds"**
- Check that your coordinates match the specified `--input-crs`
- Ensure lat/lon values aren't swapped
- Use `--preview` mode to inspect geometry before processing

**Map generation failed**
- Install optional mapping dependencies: `pip install geopandas matplotlib contextily`
- Use `--no-map` flag to skip mapping if not needed
- Check that all geometries are valid and not empty

### Performance Tips

- Use `--preview` to validate queries before processing large shapefiles
- Consider `--no-map` for batch processing to improve performance
- JSON output format includes metadata that can be used for caching decisions

## Sample Data

Test the tool using the included sample data in `sample_data/`:
- **NYC 2021 LAS index shapefile**: Real-world example from NYC Open Data
- **Sample points CSV**: Example coordinate file for testing CSV mode
- **Coverage examples**: Different scenarios to test various features