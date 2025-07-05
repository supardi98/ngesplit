import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple
import geopandas as gpd 
import shapely as shp

# Sutherland-Hodgman polygon clipping (terhadap convex polygon clip window)
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
            return None  # parallel
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
                    output_list.append(intersection(cp1, cp2, s, e))
                output_list.append(e)
            elif inside(s, cp1, cp2):
                output_list.append(intersection(cp1, cp2, s, e))
            s = e
        cp1 = cp2
    return output_list


# Fungsi utama
def split_polygon_by_count(polygon: List[Tuple[float, float]], n: int) -> List[List[Tuple[float, float]]]:
    coords = np.array(polygon)
    X, Y = coords[:, 0], coords[:, 1]
    
    # Regresi linear y = ax + b
    a, b = np.polyfit(X, Y, 1)
    direction = np.array([1, a])
    direction = direction / np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])  # tegak lurus
    
    centroid = coords.mean(axis=0)
    projections = [(pt - centroid) @ direction for pt in coords]
    min_proj, max_proj = min(projections), max(projections)
    total_length = max_proj - min_proj
    step = total_length / n

    # Buat n potongan grid
    parts = []
    for i in range(n):
        # Tentukan batas bawah dan atas potongan ke-i
        start_proj = min_proj + i * step
        end_proj = min_proj + (i + 1) * step

        # Buat kotak clipping (segiempat) tegak lurus regresi
        center1 = centroid + direction * start_proj
        center2 = centroid + direction * end_proj

        # Buat persegi panjang yang sangat panjang sepanjang normal
        L = 1e5
        p1 = center1 + normal * L
        p2 = center1 - normal * L
        p3 = center2 - normal * L
        p4 = center2 + normal * L

        clip_rect = [tuple(p1), tuple(p2), tuple(p3), tuple(p4)]
        clipped = sutherland_hodgman(polygon, clip_rect)
        if clipped:
            parts.append(clipped)
    
    return parts

def split_polygon_by_area(polygon: List[Tuple[float, float]], target_area: float) -> List[List[Tuple[float, float]]]:
    coords = np.array(polygon)
    X, Y = coords[:, 0].tolist(), coords[:, 1].tolist()
    area_total = 0.5 * abs(np.dot(X, Y[1:] + [Y[0]]) - np.dot(Y, X[1:] + [X[0]]))
    
    from math import ceil
    direction = np.array([1, np.polyfit(X, Y, 1)[0]])
    direction = direction / np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    centroid = coords.mean(axis=0)

    projections = [(pt - centroid) @ direction for pt in coords]
    min_proj, max_proj = min(projections), max(projections)
    total_length = max_proj - min_proj

    n = ceil(area_total / target_area)
    step = total_length / n

    parts = []
    for i in range(n):
        start_proj = min_proj + i * step
        end_proj = min_proj + (i + 1) * step
        center1 = centroid + direction * start_proj
        center2 = centroid + direction * end_proj
        L = 1e5
        p1 = center1 + normal * L
        p2 = center1 - normal * L
        p3 = center2 - normal * L
        p4 = center2 + normal * L
        clip_rect = [tuple(p1), tuple(p2), tuple(p3), tuple(p4)]
        clipped = sutherland_hodgman(polygon, clip_rect)
        if clipped:
            parts.append(clipped)
    return parts

