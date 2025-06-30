const express = require("express");
const multer = require("multer");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const turf = require("@turf/turf");

// Import our polygon splitting functions
const {
  splitEqualArea,
  splitByArea,
  splitHorizontalEqualArea,
  splitHorizontalByArea,
} = require("./split");

const app = express();
app.use(cors());
const upload = multer({ dest: "uploads/" });
const PORT = process.env.PORT || 3000;

// Configure directories
const UPLOAD_DIR = path.join(__dirname, "uploads");
const OUTPUT_DIR = path.join(__dirname, "outputs");

// Ensure directories exist
[UPLOAD_DIR, OUTPUT_DIR].forEach((dir) => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir);
});

const corsOptions = {
  origin: ["http://localhost:5500", "http://127.0.0.1:5500"],
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "Accept"],
  credentials: true,
  optionsSuccessStatus: 200,
};

app.use(express.json());
app.use(express.static("public"));

/**
 * Extracts all polygons from a GeoJSON feature (handles MultiPolygon)
 */
function extractPolygons(feature) {
  if (feature.geometry.type === "Polygon") {
    return [feature];
  }
  if (feature.geometry.type === "MultiPolygon") {
    return feature.geometry.coordinates.map((coords) => ({
      type: "Feature",
      properties: feature.properties || {},
      geometry: { type: "Polygon", coordinates: coords },
    }));
  }
  return [];
}

/**
 * Attempts to merge multiple polygons into one
 */
async function mergePolygons(polygons) {
  if (polygons.length === 1) return polygons[0];

  try {
    let merged = polygons[0];
    for (let i = 1; i < polygons.length; i++) {
      const union = turf.union(merged, polygons[i]);
      if (union) merged = union;
    }
    return merged;
  } catch (error) {
    console.error("Merge failed, using first polygon only:", error);
    return polygons[0];
  }
}

/**
 * Validates and prepares the input polygon
 */
async function prepareInputPolygon(geojson) {
  // Validate GeoJSON structure
  if (!geojson?.features?.length) {
    throw new Error("GeoJSON must contain at least one feature");
  }

  // Extract all polygons
  const allPolygons = [];
  for (const feature of geojson.features) {
    allPolygons.push(...extractPolygons(feature));
  }

  if (allPolygons.length === 0) {
    throw new Error("No valid Polygon or MultiPolygon features found");
  }

  // Merge polygons if there are multiple
  const mergedPolygon = await mergePolygons(allPolygons);

  // Ensure we have valid coordinates
  const coordinates = mergedPolygon.geometry.coordinates[0];
  if (!coordinates || coordinates.length < 3) {
    throw new Error("Invalid polygon coordinates");
  }

  return coordinates;
}

/**
 * Handles the splitting based on mode
 */
function performSplit(coords, mode, value) {
  switch (mode) {
    case "count":
      return splitEqualArea(coords, value);
    case "area":
      return splitByArea(coords, value);
    case "horizontal-count":
      return splitHorizontalEqualArea(coords, value);
    case "horizontal-area":
      return splitHorizontalByArea(coords, value);
    default:
      throw new Error(`Unknown split mode: ${mode}`);
  }
}

/**
 * API endpoint for polygon splitting
 */
app.post("/api/split", upload.single("geojson"), async (req, res) => {
  try {
    // Validate input
    const { mode, value } = req.body;
    const file = req.file;

    if (!file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    if (
      !mode ||
      !["count", "area", "horizontal-count", "horizontal-area"].includes(mode)
    ) {
      return res.status(400).json({ error: "Invalid mode parameter" });
    }

    const numericValue = parseFloat(value);
    if (isNaN(numericValue)) {
      return res.status(400).json({ error: "Value must be a number" });
    }

    // Read and parse GeoJSON
    const geojson = JSON.parse(fs.readFileSync(file.path));

    // Prepare input polygon
    const polygonCoords = await prepareInputPolygon(geojson);

    // Perform the split
    const splitParts = performSplit(polygonCoords, mode, numericValue);

    // Prepare result GeoJSON
    const resultFeatures = splitParts.map((part, index) => {
      // Close the ring if not already closed
      const closedRing = [...part];
      if (
        closedRing.length > 0 &&
        (closedRing[0][0] !== closedRing[closedRing.length - 1][0] ||
          closedRing[0][1] !== closedRing[closedRing.length - 1][1])
      ) {
        closedRing.push([...closedRing[0]]);
      }

      return {
        type: "Feature",
        properties: { part: index + 1 },
        geometry: {
          type: "Polygon",
          coordinates: [closedRing],
        },
      };
    });

    const resultGeoJSON = {
      type: "FeatureCollection",
      features: resultFeatures,
    };

    // Save and send result
    const outputPath = path.join(
      OUTPUT_DIR,
      `split_result_${Date.now()}.geojson`
    );
    fs.writeFileSync(outputPath, JSON.stringify(resultGeoJSON));

    res.json({
      success: true,
      downloadUrl: `./outputs/${path.basename(outputPath)}`,
      partsCount: resultFeatures.length,
    });

    // Clean up upload file
    fs.unlinkSync(file.path);
  } catch (error) {
    console.error("Split error:", error);
    res.status(500).json({
      error: "Failed to process polygon",
      details: error.message,
    });
  }
});

/**
 * Download endpoint for results
 */
app.get("/download/:filename", (req, res) => {
  // const filePath = path.join(OUTPUT_DIR, req.params.filename);
  const filePath = "./outputs/";
  if (fs.existsSync(filePath)) {
    res.download(filePath, "split_result.geojson", () => {
      // Clean up the file after download
      fs.unlinkSync(filePath);
    });
  } else {
    res.status(404).send("File not found");
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

process.on("unhandledRejection", (err) => {
  console.error("Unhandled rejection:", err);
});
