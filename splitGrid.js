const proj4 = require("proj4");

// Hapus ini kalau inputmu sudah EPSG:3857
const project = proj4("EPSG:4326", "EPSG:3857");
const unproject = proj4("EPSG:3857", "EPSG:4326");

/** Project ring */
function projectRing(ring) {
  return ring.map((coord) => project.forward(coord));
}
function unprojectRing(ring) {
  return ring.map((coord) => unproject.inverse(coord));
}

/** Check if two segments intersect a Y line */
function segmentIntersectsY([a, b], y) {
  return (a[1] <= y && b[1] >= y) || (a[1] >= y && b[1] <= y);
}

/** Find X where a segment intersects Y */
function intersectXAtY([a, b], y) {
  const dy = b[1] - a[1];
  if (dy === 0) return a[0];
  const t = (y - a[1]) / dy;
  return a[0] + t * (b[0] - a[0]);
}

/** Clip polygon between yMin and yMax */
function clipPolygonHorizontally(ring, yMin, yMax) {
  const result = [];

  for (let i = 0; i < ring.length; i++) {
    const a = ring[i];
    const b = ring[(i + 1) % ring.length];

    if (segmentIntersectsY([a, b], yMin)) {
      const x = intersectXAtY([a, b], yMin);
      if (isFinite(x)) result.push([x, yMin]);
    }

    if (a[1] >= yMin && a[1] <= yMax) {
      result.push(a);
    }

    if (segmentIntersectsY([a, b], yMax)) {
      const x = intersectXAtY([a, b], yMax);
      if (isFinite(x)) result.push([x, yMax]);
    }
  }

  // Polygon minimal 4 titik
  if (result.length < 4) return [];

  // Tutup polygon
  const first = result[0];
  const last = result.at(-1);
  if (first[0] !== last[0] || first[1] !== last[1]) {
    result.push([...first]);
  }

  return result;
}

/** Main function: input GeoJSON polygon (EPSG:4326), output sliced GeoJSONs */
function slicePolygon(polygonFeature, n) {
  if (
    !polygonFeature ||
    polygonFeature.type !== "Feature" ||
    polygonFeature.geometry.type !== "Polygon"
  ) {
    throw new Error("❌ Input must be a GeoJSON Feature with Polygon geometry");
  }

  const ring4326 = polygonFeature.geometry.coordinates[0];

  // Project to EPSG:3857
  const ring3857 = projectRing(ring4326);
  const ys = ring3857.map((p) => p[1]);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const step = (maxY - minY) / n;

  const slices = [];

  for (let i = 0; i < n; i++) {
    const y0 = minY + i * step;
    const y1 = y0 + step;

    const clipped = clipPolygonHorizontally(ring3857, y0, y1);
    if (clipped.length >= 4) {
      const unprojected = unprojectRing(clipped);
      slices.push({
        type: "Feature",
        properties: { slice: i },
        geometry: {
          type: "Polygon",
          coordinates: [unprojected],
        },
      });
    }
  }

  return {
    type: "FeatureCollection",
    features: slices,
  };
}

module.exports = {
  slicePolygon,
};
