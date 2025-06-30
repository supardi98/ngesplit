/**
 * Utility functions for polygon splitting
 * - All coordinates are in UTM (meters)
 * - All areas are in square meters
 */

/** Shoelace formula to compute polygon area */
function shoelaceArea(points) {
  let area = 0;
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % n];
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2;
}

/** Linear interpolation between two points */
function interpolate(p1, p2, t) {
  return [p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])];
}

/** Clip polygon between two y-values (horizontal slicing) */
function clipHorizontal(polygon, yMin, yMax) {
  const clipped = [];
  const n = polygon.length;

  for (let i = 0; i < n; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % n];
    const [x1, y1] = a;
    const [x2, y2] = b;

    // Check if point is within bounds
    if (y1 >= yMin && y1 <= yMax) clipped.push(a);

    // Check for intersection with bottom boundary
    if ((y1 < yMin && y2 > yMin) || (y1 > yMin && y2 < yMin)) {
      const t = (yMin - y1) / (y2 - y1);
      clipped.push([x1 + t * (x2 - x1), yMin]);
    }

    // Check for intersection with top boundary
    if ((y1 < yMax && y2 > yMax) || (y1 > yMax && y2 < yMax)) {
      const t = (yMax - y1) / (y2 - y1);
      clipped.push([x1 + t * (x2 - x1), yMax]);
    }
  }

  // Close the polygon if needed
  if (
    clipped.length > 0 &&
    (clipped[0][0] !== clipped[clipped.length - 1][0] ||
      clipped[0][1] !== clipped[clipped.length - 1][1])
  ) {
    clipped.push([...clipped[0]]);
  }

  return clipped;
}

/** Split polygon between two edges at given interpolation values */
function splitAtEdges(polygon, i, j, ti, tj) {
  const n = polygon.length;
  const pi = interpolate(polygon[i], polygon[(i + 1) % n], ti);
  const pj = interpolate(polygon[j], polygon[(j + 1) % n], tj);

  // First polygon (i → j)
  const poly1 = [pi];
  for (let k = (i + 1) % n; k !== (j + 1) % n; k = (k + 1) % n) {
    poly1.push(polygon[k]);
  }
  poly1.push(pj);

  // Second polygon (j → i)
  const poly2 = [pj];
  for (let k = (j + 1) % n; k !== (i + 1) % n; k = (k + 1) % n) {
    poly2.push(polygon[k]);
  }
  poly2.push(pi);

  return [poly1, poly2];
}

/** Find optimal split to achieve target area */
function findOptimalSplit(polygon, targetArea, steps = 10, tolerance = 0.05) {
  const n = polygon.length;
  let bestSplit = null;
  let bestDiff = Infinity;

  // Try all possible edge combinations
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      // Skip adjacent edges and same edge
      if (Math.abs(i - j) < 2 || Math.abs(i - j) > n - 2) continue;

      // Try different interpolation points
      for (let si = 1; si < steps; si++) {
        for (let sj = 1; sj < steps; sj++) {
          const ti = si / steps;
          const tj = sj / steps;
          const [poly1, poly2] = splitAtEdges(polygon, i, j, ti, tj);
          const area = shoelaceArea(poly1);
          const diff = Math.abs(area - targetArea);

          if (diff < bestDiff) {
            bestDiff = diff;
            bestSplit = [poly1, poly2];
          }

          // Early exit if within tolerance
          if (diff < tolerance * targetArea) {
            return [poly1, poly2];
          }
        }
      }
    }
  }
  return bestSplit;
}

// Main splitting functions ==============================================

/**
 * 1. Split polygon into N parts with equal area (arbitrary cuts)
 * @param {Array} coords - Polygon coordinates in UTM [[x,y], ...]
 * @param {number} count - Number of parts to split into
 * @returns {Array} Array of split polygons
 */
function splitEqualArea(coords, count) {
  if (!Array.isArray(coords)) throw new Error("Coordinates must be an array");
  if (count <= 0 || !Number.isInteger(count))
    throw new Error("Count must be positive integer");

  const parts = [];
  let current = [...coords];
  const totalArea = shoelaceArea(current);

  for (let i = 0; i < count - 1; i++) {
    const remainingArea = shoelaceArea(current);
    const target = remainingArea / (count - i);
    const cut = findOptimalSplit(current, target);

    if (!cut) break;
    parts.push(cut[0]);
    current = cut[1];
  }

  parts.push(current);
  return parts;
}

/**
 * 2. Split polygon into parts with specified area (arbitrary cuts)
 * @param {Array} coords - Polygon coordinates in UTM [[x,y], ...]
 * @param {number} area - Target area for each part (m²)
 * @returns {Array} Array of split polygons
 */
function splitByArea(coords, area) {
  if (!Array.isArray(coords)) throw new Error("Coordinates must be an array");
  if (area <= 0) throw new Error("Area must be positive");

  const totalArea = shoelaceArea(coords);
  const count = Math.max(1, Math.round(totalArea / area));
  return splitEqualArea(coords, count);
}

/**
 * 3. Split polygon horizontally into N equal area parts
 * @param {Array} coords - Polygon coordinates in UTM [[x,y], ...]
 * @param {number} count - Number of parts to split into
 * @returns {Array} Array of split polygons
 */
function splitHorizontalEqualArea(coords, count) {
  if (!Array.isArray(coords)) throw new Error("Coordinates must be an array");
  if (count <= 0 || !Number.isInteger(count))
    throw new Error("Count must be positive integer");

  const ys = coords.map((p) => p[1]);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const totalArea = shoelaceArea(coords);
  const targetArea = totalArea / count;

  const parts = [];
  let currentY = minY;
  let remaining = [...coords];

  for (let i = 0; i < count - 1; i++) {
    let low = currentY;
    let high = maxY;
    let bestSlice = null;

    // Binary search for optimal split position
    for (let iter = 0; iter < 20; iter++) {
      const midY = (low + high) / 2;
      const slice = clipHorizontal(remaining, currentY, midY);
      const area = shoelaceArea(slice);

      if (Math.abs(area - targetArea) < 0.01 * targetArea) {
        bestSlice = slice;
        break;
      }

      if (area < targetArea) low = midY;
      else high = midY;
    }

    if (!bestSlice) {
      // Fallback if binary search fails
      bestSlice = clipHorizontal(
        remaining,
        currentY,
        currentY + (maxY - currentY) / (count - i)
      );
    }

    parts.push(bestSlice);
    currentY = bestSlice[bestSlice.length - 1][1]; // Get maxY from last point
    remaining = clipHorizontal(remaining, currentY, maxY);
  }

  if (remaining.length > 0) {
    parts.push(remaining);
  }

  return parts;
}

/**
 * 4. Split polygon horizontally into parts with specified area
 * @param {Array} coords - Polygon coordinates in UTM [[x,y], ...]
 * @param {number} area - Target area for each part (m²)
 * @returns {Array} Array of split polygons
 */
function splitHorizontalByArea(coords, area) {
  if (!Array.isArray(coords)) throw new Error("Coordinates must be an array");
  if (area <= 0) throw new Error("Area must be positive");

  const totalArea = shoelaceArea(coords);
  const count = Math.max(1, Math.round(totalArea / area));
  return splitHorizontalEqualArea(coords, count);
}

module.exports = {
  splitEqualArea, // 1. Potong sembarang, sama luas, jumlah ditentukan
  splitByArea, // 2. Potong sembarang, luas ditentukan
  splitHorizontalEqualArea, // 3. Potong horizontal, sama luas, jumlah ditentukan
  splitHorizontalByArea, // 4. Potong horizontal, luas ditentukan
  shoelaceArea, // Expose for testing
};
