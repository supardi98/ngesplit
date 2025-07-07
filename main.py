from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
import os
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from ngesplit import split_polygon_by_area, split_polygon_by_count
import json;

app = Flask(__name__)
CORS(app)

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
        for part in parts:
            if isinstance(part, (Polygon, MultiPolygon)):
                all_parts.append(part)
            else:
                all_parts.append(Polygon(part))
    return gpd.GeoDataFrame(geometry=gpd.GeoSeries(all_parts), crs="EPSG:4326")

# open index.html
@app.route('/', methods=['GET'])
def index():
    return app.send_static_file('index.html')

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
    gdf_utm = gdf.to_crs("EPSG:3857")
    result = split_polygon(gdf_utm, mode, val)

    # Reproject result back to original CRS (if defined)
    if original_crs:
        result = result.set_crs("EPSG:3857",allow_override=True).to_crs(original_crs)

    # Save result using original CRS
    output_path = os.path.join(PROCESSED_FOLDER, 'hasil_split.geojson')
    result.to_file(output_path, driver="GeoJSON")
    geojson = result.to_json()

    # Also save WGS84 version for Leaflet preview
    preview_path = os.path.join(PROCESSED_FOLDER, 'preview.geojson')
    result.to_crs("EPSG:4326").to_file(preview_path, driver="GeoJSON")

    # open raw data
    return jsonify({
        'message': 'File processed',
        'download': '/download/hasil_split.geojson',
        'preview': '/download/preview.geojson',
        'result_geojson': json.loads(geojson)
    })

@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=False)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
