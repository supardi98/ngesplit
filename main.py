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
    return gpd.GeoSeries(all_parts)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    mode = request.form.get('mode', type=int)
    val = request.form.get('val', type=float)

    if not file or mode is None or val is None:
        return jsonify({'error': 'File, mode, and val are required'}), 400

    filepath = os.path.join(PROCESSED_FOLDER, 'input.geojson')
    file.save(filepath)

    # Load and process
    gdf = gpd.read_file(filepath)
    result_series = split_polygon(gdf, mode, val)
    output_path = os.path.join(PROCESSED_FOLDER, 'hasil_split.geojson')
    result_series.to_file(output_path, driver="GeoJSON")

    return jsonify({'message': 'File processed', 'download': '/download/hasil_split.geojson'}), 200

@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
