from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
import os
import geopandas as gpd
import shapely.ops as ops
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, MultiLineString
from ngesplit import split_polygon_by_area, split_polygon_by_count
import json;
import math
import numpy as np

app = Flask(__name__)
CORS(app)

PROCESSED_FOLDER = 'processed'
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def fix_polygon(geom):
    # Jika geom adalah fitur shapely sudah benar
    if isinstance(geom, Polygon) or isinstance(geom, MultiPolygon):
        return geom

    # Jika geometry-nya malah mengandung geometry di dalam coordinates
    if isinstance(geom, dict) and "type" in geom and geom["type"] == "Polygon":
        coords = geom["coordinates"]

        # kalau nested 2x → buang satu nesting
        # contoh: [[[ [x,y], [x,y] ]]]
        if len(coords) == 1 and isinstance(coords[0], list) and len(coords[0]) == 1:
            coords = coords[0]

        return Polygon(coords[0])

    raise ValueError("Geometry polygon tidak valid")

def format_geojson_result(gdf, name="result"):
    """Format GeoDataFrame ke format GeoJSON yang sesuai"""
    if gdf is None or gdf.empty:
        return {
            "type": "FeatureCollection",
            "name": name,
            "features": []
        }
    
    # Konversi ke GeoJSON
    geojson = json.loads(gdf.to_json())
    
    # Format sesuai dengan yang diminta
    formatted_geojson = {
        "type": "FeatureCollection",
        "name": name,
        "features": []
    }
    
    for index,feature in enumerate(list(geojson['features'])):
        formatted_feature = {
            "type": "Feature",
            "properties": {},
            "geometry": feature['geometry'],
            "id":index
        }
        formatted_geojson['features'].append(formatted_feature)
    
    return formatted_geojson

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

@app.route('/cut', methods=['POST'])
def cut_polygon():
    try:
        data = request.get_json()

        # Load with GeoPandas
        poly_gdf = gpd.GeoDataFrame.from_features([data["polygon"]], crs="EPSG:4326")
        line_gdf = gpd.GeoDataFrame.from_features([data["line"]], crs="EPSG:4326")
        print(line_gdf)

        poly = poly_gdf.geometry.iloc[0]
        line = line_gdf.geometry.iloc[0]

        # --------------------------------------------
        # 🔥 FIX DI SINI: PAKSA PERBAIKI POLYGON BERAPAPUN ERRORNYA
        # --------------------------------------------
        poly = poly.buffer(0)   # <= INI YANG MEMBUAT ERROR 'create_collection' HILANG

        if poly.is_empty:
            return jsonify({"success": False, "error": "Polygon rusak dan tidak bisa diperbaiki."})

        # --------------------------------------------
        # Extend line
        # --------------------------------------------
        minx, miny, maxx, maxy = poly.bounds
        dx = line.coords[-1][0] - line.coords[0][0]
        dy = line.coords[-1][1] - line.coords[0][1]
        L = (dx*dx + dy*dy)**0.5
        dx /= L; dy /= L

        far = max(maxx - minx, maxy - miny) * 1000
        start = (line.coords[0][0] - dx*far, line.coords[0][1] - dy*far)
        end   = (line.coords[-1][0] + dx*far, line.coords[-1][1] + dy*far)
        ext_line = LineString([start, end])

        # --------------------------------------------
        # Split
        # --------------------------------------------
        # print(poly,line)
        try:
            res = ops.split(poly, line)
            print(list(res.geoms))
        except Exception as e:
            return jsonify({"success": False, "error": f"Split gagal: {str(e)}"})

        pieces = [g for g in list(res.geoms)]

        if len(pieces) < 2:
            return jsonify({"success": False, "error": "Garis tidak membelah polygon."})

        out = gpd.GeoDataFrame(geometry=pieces, crs="EPSG:4326").__geo_interface__

        return jsonify({"success": True, "result": out})

    except Exception as e:
        return jsonify({"success": False, "error": f"{str(e)}"})


@app.route('/grid', methods=['POST'])
def create_grid():
    try:
        data = request.get_json()
        
        # Validasi input
        if not data or 'polygon' not in data or 'line' not in data:
            return jsonify({"success": False, "error": "Data polygon dan line diperlukan"})
        
        rows = data.get('rows', 2)
        cols = data.get('cols', 2)
        
        # Konversi ke GeoDataFrame
        polygon_feature = data['polygon']
        line_feature = data['line']
        
        # Buat GeoDataFrame dari polygon
        polygon_gdf = gpd.GeoDataFrame.from_features([polygon_feature], crs="EPSG:4326")
        polygon_geom = polygon_gdf.geometry.iloc[0]
        line_gdf = gpd.GeoDataFrame.from_features([line_feature], crs="EPSG:4326")

        # Buat LineString dari feature garis
        line_coords = line_feature['geometry']['coordinates']
        line_geom = LineString(line_coords)
        linex,liney = gpd.clip(line_gdf,polygon_gdf)["geometry"].iloc[0].xy
        
        # Dapatkan bounds dari polygon
        minx, miny, maxx, maxy = polygon_geom.bounds
        
        # Hitung orientasi garis untuk menentukan arah grid
        line_coords_array = np.array([list(linex),list(liney)]).T
        line_vector = line_coords_array[-1] - line_coords_array[0]
        line_angle = np.arctan2(line_vector[1], line_vector[0])
        line_centroid = Point(np.mean(line_coords_array,axis=0))
        # Buat grid berdasarkan orientasi garis
        width = maxx - minx
        height = maxy - miny
        c = np.array([[minx+(maxx-minx)/2,miny+(maxy-miny)/2]])
        # diff = line_centroid-c
        print(line_centroid)
        # width = line_geom.length
        # Buat grid dalam bounding box polygon
        grid_cells = []
        grid_lines = []
        LARGE = 1  # garis super panjang

        # vertical lines
        for j in range(cols + 1):
            offset = (j - cols/2) * (width / cols)
            x = line_centroid.x + offset
            line = LineString([(x, line_centroid.y - LARGE), (x, line_centroid.y + LARGE)])
            rotated = rotate(line, line_angle, origin=line_centroid, use_radians=True)
            grid_lines.append(rotated)

        # horizontal lines
        for i in range(rows + 1):
            offset = (i - rows/2) * (width / rows)
            y = line_centroid.y + offset
            line = LineString([(line_centroid.x - LARGE, y), (line_centroid.x + LARGE, y)])
            rotated = rotate(line, line_angle, origin=line_centroid, use_radians=True)
            grid_lines.append(rotated)

        # ================
        # 2) Hitung centroid grid dan offset ke line_centroid
        # ================

        multi = MultiLineString(grid_lines)
        current_center = multi.centroid

        dx = line_centroid.x - current_center.x
        dy = line_centroid.y - current_center.y

        grid_lines = [translate(line, dx, dy) for line in grid_lines]

        # ================
        # 3) Final GeoDataFrame
        # ================
        grid_cells = gpd.GeoDataFrame(geometry=grid_lines, crs="EPSG:4326")
        print(grid_cells.geometry,polygon_gdf.geometry)
        # Buat GeoDataFrame dari grid cells
        if len(grid_lines) > 0:
            multi_line = MultiLineString(grid_lines)

            # split polygon
            split_result = ops.split(polygon_gdf.geometry.iloc[0], multi_line)
            line 
            # convert to gdf
            grid_cells = gpd.GeoDataFrame(geometry=gpd.GeoSeries(split_result.geoms), crs="EPSG:4326")

            result_geojson = format_geojson_result(grid_cells,"result")

            return jsonify({
                "success": True,
                "result": result_geojson
            })
        else:
            return jsonify({"success": False, "error": "Tidak ada grid yang dihasilkan"})
            
    except Exception as e:
        return jsonify({"success": False, "error": f"Error sdsdf: {str(e)}"})
    
@app.route('/split-by-area', methods=['POST'])
def split_by_area():
    try:
        data = request.get_json()
        if not data or 'bidang' not in data or 'target_area' not in data or 'degree' not in data:
            return jsonify({"success": False, "error": "bidang, degree, dan target_area wajib ada"})

        target_area = float(data['target_area'])  # m²
        degree = float(data['degree'])            # derajat 0–360
        polygon_feature = data['bidang']

        # Convert polygon → GeoDataFrame metric CRS
        polygon_gdf = gpd.GeoDataFrame.from_features([polygon_feature], crs="EPSG:4326").to_crs(3857)
        polygon = polygon_gdf.geometry.iloc[0]

        if polygon.is_empty:
            return jsonify({"success": False, "error": "polygon empty"})

        # ======================================================
        # 1. Compute direction vector from angle
        # ======================================================
        rad = math.radians(degree)

        # direction (unit vector)
        dx = math.cos(rad)
        dy = math.sin(rad)

        # perpendicular normal
        nx = -dy
        ny = dx

        # Normal vector already unit length because cos/sin

        # ======================================================
        # 2. Sweep range: project all polygon vertices on normal
        # ======================================================
        projs = []
        for (px, py) in polygon.exterior.coords:
            projs.append(px * nx + py * ny)
        for interior in polygon.interiors:
            for (px, py) in interior.coords:
                projs.append(px * nx + py * ny)

        sweep_min = min(projs)
        sweep_max = max(projs)

        cx, cy = polygon.centroid.x, polygon.centroid.y
        centroid_proj = cx * nx + cy * ny

        remaining = polygon
        split_lines = []
        last_t = sweep_min
        max_iterations = 500

        # helper splitting
        def try_split_by_line(poly, cut_line, current_t):
            try:
                parts = ops.split(poly, cut_line)
            except Exception:
                return None, None

            if len(parts.geoms) < 2:
                return None, None

            left_parts = []
            right_parts = []

            for g in parts.geoms:
                gx, gy = g.centroid.x, g.centroid.y
                gproj = gx * nx + gy * ny
                if gproj <= current_t:
                    left_parts.append(g)
                else:
                    right_parts.append(g)

            if not left_parts or not right_parts:
                return None, None

            return ops.unary_union(left_parts), ops.unary_union(right_parts)

        # ======================================================
        # 3. Sweep with binary search
        # ======================================================
        iterations = 0
        while remaining.area > target_area and iterations < max_iterations:
            iterations += 1
            low, high = last_t, sweep_max
            current_t = None

            # Binary search 50 steps
            for _ in range(50):
                mid = (low + high) / 2
                current_t = mid

                # point on normal at t
                shift = mid - centroid_proj
                px = cx + nx * shift
                py = cy + ny * shift

                # very long "cut" line
                L = 9999999
                cut_line = LineString([
                    (px - dx * L, py - dy * L),
                    (px + dx * L, py + dy * L)
                ])

                left, right = try_split_by_line(remaining, cut_line, current_t)
                if left is None:
                    low = mid
                    continue

                if left.area < target_area:
                    low = mid
                else:
                    high = mid

            # final line
            cut_t = (low + high) / 2
            shift = cut_t - centroid_proj
            px = cx + nx * shift
            py = cy + ny * shift

            final_cut = LineString([
                (px - dx * L, py - dy * L),
                (px + dx * L, py + dy * L)
            ])

            left, right = try_split_by_line(remaining, final_cut, cut_t)
            if left is None or right is None:
                break

            split_lines.append(final_cut)
            remaining = right
            last_t = cut_t

        # ======================================================
        # 4. Clip & return output
        # ======================================================
        clipped_lines = []
        buff = polygon.buffer(100)
        for ln in split_lines:
            cut = ln.intersection(buff)
            if cut.is_empty: continue
            if cut.geom_type == "MultiLineString":
                clipped_lines.extend(list(cut.geoms))
            else:
                clipped_lines.append(cut)

        result_gdf = (
            gpd.GeoDataFrame(geometry=clipped_lines, crs="EPSG:3857").to_crs(4326)
            if clipped_lines else
            gpd.GeoDataFrame(columns=["geometry"], geometry=[], crs="EPSG:4326")
        )

        return jsonify({
            "success": True,
            "result": json.loads(result_gdf.to_json())
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/cut_normal', methods=['POST'])
def cut_normal():
    try:
        data = request.get_json()
        
        # Validasi input
        if not data or 'bidang' not in data or 'line' not in data:
            return jsonify({"success": False, "error": "Data polygon dan line diperlukan"})
        
        # Konversi ke GeoDataFrame
        polygon_feature = data['bidang']
        line_feature = data['line']["features"]
        print(polygon_feature)
        # Buat GeoDataFrame dari polygon
        polygon_gdf = gpd.GeoDataFrame.from_features([polygon_feature], crs="EPSG:4326")
        
        polygon_geom = polygon_gdf.geometry.iloc[0]
        # line_gdf = gpd.GeoDataFrame.from_features([line_feature], crs="EPSG:4326")
        
        # Buat LineString dari feature garis
        line_coords = [i['geometry']['coordinates'] for i in line_feature]
        line_geom = MultiLineString(line_coords)
        
        # Buat GeoDataFrame dari grid cells
        if len(line_coords) > 0:
            # multi_line = MultiLineString([i for i in line_geom])

            # split polygon
            split_result = ops.split(polygon_geom, line_geom)
            # line 
            # convert to gdf
            grid_cells = gpd.GeoDataFrame(geometry=gpd.GeoSeries(split_result.geoms), crs="EPSG:4326")
            
            result_geojson = format_geojson_result(grid_cells,"result")

            return jsonify({
                "success": True,
                "result": result_geojson
            })
        else:
            result_geojson = format_geojson_result(polygon_gdf,"result")
            return jsonify({
                "success": True,
                "result": result_geojson
            })
        # else:
        #     return jsonify({"success": False, "error": "Tidak perpotongan yang dihasilkan "})
            
    except Exception as e:
        return jsonify({"success": False, "error": f"Error sdsdf: {str(e)}"})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "OK", "message": "GeoJSON Grid Tool API is running"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
