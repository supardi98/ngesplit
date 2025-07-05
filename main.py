from flask import Flask, request, send_from_directory, jsonify
import os
import geopandas as gpd
from shapely.geometry import Polygon
from ngesplit import split_polygon_by_area, split_polygon_by_count

app = Flask(__name__)
PROCESSED_FOLDER = 'processed'
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def split_polygon(gdf, mode, val): 
    all_parts = []
    for geom in gdf.geometry:
        if geom.geom_type == "Polygon":
            coords = list(geom.exterior.coords)
        elif geom.geom_type == "MultiPolygon":
            coords = list(geom.geoms[0].exterior.coords)
        else:
            continue
        if mode == 0:
            parts = split_polygon_by_count(coords, int(val))
        elif mode == 1:
            parts = split_polygon_by_area(coords, val)
        for part_coords in parts:
            all_parts.append(Polygon(part_coords))
    return gpd.GeoDataFrame(geometry=gpd.GeoSeries(all_parts), crs="EPSG:4326")

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    mode = request.form.get('mode', type=int)
    val = request.form.get('val', type=float)

    if not file or mode is None or val is None:
        return jsonify({'error': 'File, mode, and val are required'}), 400

    input_path = os.path.join(PROCESSED_FOLDER, 'input.geojson')
    file.save(input_path)

    gdf = gpd.read_file(input_path)

    # Store original CRS
    original_crs = gdf.crs

    # Reproject to WGS84 for processing & preview
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    result = split_polygon(gdf, mode, val)

    # Reproject result back to original CRS (if defined)
    if original_crs:
        result = result.set_crs(original_crs,allow_override=True)

    # Save result using original CRS
    output_path = os.path.join(PROCESSED_FOLDER, 'hasil_split.geojson')
    result.to_file(output_path, driver="GeoJSON")

    # Also save WGS84 version for Leaflet preview
    preview_path = os.path.join(PROCESSED_FOLDER, 'preview.geojson')
    result.to_crs("EPSG:4326").to_file(preview_path, driver="GeoJSON")

    return jsonify({
        'message': 'File processed',
        'download': '/download/hasil_split.geojson',
        'preview': '/download/preview.geojson'
    })

@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=False)

if __name__ == '__main__':
    app.run(debug=True)
