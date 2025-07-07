import numpy as np
from typing import List, Tuple
from shapely.geometry import MultiPolygon, LineString,Polygon
from shapely.ops import polygonize
from math import isfinite


# Sutherland-Hodgman Clipping
def sutherland_hodgman(subject_polygon, clip_polygon):
    def inside(p, cp1, cp2):
        return (cp2[0] - cp1[0]) * (p[1] - cp1[1]) > (cp2[1] - cp1[1]) * (p[0] - cp1[0])

    def intersection(cp1, cp2, s, e):
        dc = (cp1[0] - cp2[0], cp1[1] - cp2[1])
        dp = (s[0] - e[0], s[1] - e[1])
        n1 = cp1[0] * cp2[1] - cp1[1] * cp2[0]
        n2 = s[0] * e[1] - s[1] * e[0]
        denom = dc[0] * dp[1] - dc[1] * dp[0]
        if denom == 0:
            return None
        x = (n1 * dp[0] - n2 * dc[0]) / denom
        y = (n1 * dp[1] - n2 * dc[1]) / denom
        return (x, y)

    output_list = subject_polygon
    cp1 = clip_polygon[-1]
    for cp2 in clip_polygon:
        input_list = output_list
        output_list = []
        if not input_list:
            return []
        s = input_list[-1]
        for e in input_list:
            if inside(e, cp1, cp2):
                if not inside(s, cp1, cp2):
                    inter = intersection(cp1, cp2, s, e)
                    if inter:
                        output_list.append(inter)
                output_list.append(e)
            elif inside(s, cp1, cp2):
                inter = intersection(cp1, cp2, s, e)
                if inter:
                    output_list.append(inter)
            s = e
        cp1 = cp2
    return output_list


# Clipping Rectangle Generator
def clip_polygon_with_projection(polygon, centroid, direction, start_proj, end_proj):
    normal = np.array([-direction[1], direction[0]])
    center1 = centroid + direction * start_proj
    center2 = centroid + direction * end_proj
    L = 1e5
    p1 = center1 + normal * L
    p2 = center1 - normal * L
    p3 = center2 - normal * L
    p4 = center2 + normal * L
    clip_rect = [tuple(p1), tuple(p2), tuple(p3), tuple(p4)]
    return sutherland_hodgman(polygon, clip_rect)


# Fix to valid polygon

def to_valid_polygon(coords):
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)

    if poly.is_empty:
        return None

    lines = [LineString(coords)]
    polys = list(polygonize(lines))

    if len(polys) == 1:
        return polys[0]
    elif len(polys) > 1:
        return MultiPolygon(polys)
    else:
        return poly

def split_polygon_by_area(polygon: List[Tuple[float, float]], target_area: float) -> List[Polygon]:
    coords = np.array(polygon)
    if len(coords) < 4:
        return []

    X, Y = coords[:, 0], coords[:, 1]
    try:
        a, _ = np.polyfit(X, Y, 1)
        direction = np.array([1, a]) if isfinite(a) else np.array([0, 1])
    except:
        direction = np.array([1, 0])
    direction = direction / np.linalg.norm(direction)

    centroid = coords.mean(axis=0)
    projections = [(pt - centroid) @ direction for pt in coords]
    min_proj, max_proj = min(projections), max(projections)

    parts = []
    current_proj = min_proj
    total_area = Polygon(polygon).area

    while True:
        low = current_proj
        high = max_proj
        best_proj = None

        for _ in range(200):
            mid = (low + high) / 2
            clipped_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, mid)
            if not clipped_coords:
                break
            clipped_poly = to_valid_polygon(clipped_coords)
            area = clipped_poly.area
            if abs(area - target_area) / target_area < 0.00005:
                best_proj = mid
                break
            elif area > target_area:
                high = mid
            else:
                low = mid

        if best_proj is None:
            break

        clipped_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, best_proj)
        if clipped_coords:
            clipped_poly = to_valid_polygon(clipped_coords)
            parts.append(clipped_poly)
            current_proj = best_proj
        else:
            break

    # ✅ Masukkan sisa polygon terakhir
    last_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, max_proj)
    if last_coords:
        last_poly = to_valid_polygon(last_coords)
        parts.append(last_poly)

    return parts

def split_polygon_by_count(polygon: List[Tuple[float, float]], n: int) -> List[Polygon]:
    coords = np.array(polygon)
    if len(coords) < 4:
        return []

    X, Y = coords[:, 0], coords[:, 1]
    try:
        a, _ = np.polyfit(X, Y, 1)
        direction = np.array([1, a]) if isfinite(a) else np.array([0, 1])
    except:
        direction = np.array([1, 0])
    direction = direction / np.linalg.norm(direction)

    centroid = coords.mean(axis=0)
    projections = [(pt - centroid) @ direction for pt in coords]
    min_proj, max_proj = min(projections), max(projections)
    total_area = Polygon(polygon).area
    target_area = total_area / n

    parts = []
    current_proj = min_proj
    for i in range(n - 1):  # Lakukan n-1 kali
        low = current_proj
        high = max_proj
        best_proj = None

        for _ in range(200):
            mid = (low + high) / 2
            clipped_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, mid)
            if not clipped_coords:
                break
            clipped_poly = to_valid_polygon(clipped_coords)
            area = clipped_poly.area
            if abs(area - target_area) / target_area < 0.00005:
                best_proj = mid
                break
            elif area > target_area:
                high = mid
            else:
                low = mid

        if best_proj is None:
            break

        clipped_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, best_proj)
        if clipped_coords:
            clipped_poly = to_valid_polygon(clipped_coords)
            parts.append(clipped_poly)
            current_proj = best_proj
        else:
            break

    # ✅ Masukkan sisa terakhir sebagai potongan ke-n
    final_coords = clip_polygon_with_projection(polygon, centroid, direction, current_proj, max_proj)
    if final_coords:
        clipped_poly = to_valid_polygon(final_coords)
        parts.append(clipped_poly)

    return parts
