"""
Building extraction module using segment-geospatial (SAM2)
This module provides functionality to extract buildings from satellite imagery
using the Segment Anything Model 2 (SAM2).
"""

import os
import tempfile
import streamlit as st
import geopandas as gpd
from samgeo import SamGeo2
import leafmap
import json
from shapely.geometry import shape, box
from pathlib import Path
import gc

# Disable GPU for Streamlit cloud deployment
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

def download_satellite_imagery(bbox, zoom=19, output_dir=None):
    """
    Download satellite imagery for a given bounding box.

    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
        zoom: Zoom level for the imagery (default 19 for high resolution)
        output_dir: Directory to save the imagery (if None, uses temp dir)

    Returns:
        Path to the downloaded GeoTIFF file
    """
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "satellite_image.tif")

    try:
        st.info(f"Downloading satellite imagery at zoom level {zoom}...")

        # Download imagery using leafmap
        leafmap.map_tiles_to_geotiff(
            output=output_path,
            bbox=bbox,
            zoom=zoom,
            source="Satellite",  # Uses Esri World Imagery
            overwrite=True
        )

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            st.success("Satellite imagery downloaded successfully!")
            return output_path
        else:
            st.error("Failed to download satellite imagery")
            return None

    except Exception as e:
        st.error(f"Error downloading satellite imagery: {str(e)}")
        return None


def extract_buildings_sam2(image_path, output_dir=None):
    """
    Extract buildings from satellite imagery using SAM2.

    Args:
        image_path: Path to the input GeoTIFF image
        output_dir: Directory to save the results (if None, uses temp dir)

    Returns:
        Path to the output GeoPackage file containing building polygons
    """
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    os.makedirs(output_dir, exist_ok=True)

    masks_path = os.path.join(output_dir, "building_masks.tif")
    output_path = os.path.join(output_dir, "buildings.gpkg")

    try:
        st.info("Initializing SAM2 model...")

        # Initialize SAM2 with automatic mode
        sam2 = SamGeo2(
            model_id="sam2-hiera-large",
            automatic=True,
            points_per_side=32,  # Adjust for performance vs accuracy
            pred_iou_thresh=0.86,  # Higher threshold for better quality
            stability_score_thresh=0.92,  # Higher for more stable predictions
            min_mask_region_area=100,  # Minimum area in pixels (filters small objects)
        )

        st.info("Running building detection (this may take a few minutes)...")

        # Generate masks
        sam2.generate(image_path)

        # Save masks as raster
        sam2.save_masks(output=masks_path)

        st.info("Converting masks to vector format...")

        # Convert raster masks to vector format (GeoPackage)
        sam2.raster_to_vector(masks_path, output_path)

        # Clean up temporary files
        if os.path.exists(masks_path):
            os.remove(masks_path)

        # Force garbage collection
        del sam2
        gc.collect()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            st.success(f"Building extraction completed! Found buildings in {output_path}")
            return output_path
        else:
            st.error("Building extraction failed - no output generated")
            return None

    except Exception as e:
        st.error(f"Error extracting buildings: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None


def filter_buildings_by_geometry(buildings_path, filter_geometry):
    """
    Filter extracted buildings by a given geometry.

    Args:
        buildings_path: Path to the GeoPackage file containing building polygons
        filter_geometry: Shapely geometry to filter by

    Returns:
        GeoDataFrame of filtered buildings
    """
    try:
        # Read the buildings
        buildings_gdf = gpd.read_file(buildings_path)

        if buildings_gdf.empty:
            st.warning("No buildings found in the extracted data")
            return buildings_gdf

        # Filter by intersection with the input geometry
        filtered_buildings = buildings_gdf[buildings_gdf.intersects(filter_geometry)]

        return filtered_buildings

    except Exception as e:
        st.error(f"Error filtering buildings: {str(e)}")
        return gpd.GeoDataFrame()


def filter_buildings_by_size(buildings_gdf, min_area_sqm=10, max_area_sqm=10000):
    """
    Filter buildings by area (in square meters).

    Args:
        buildings_gdf: GeoDataFrame of buildings
        min_area_sqm: Minimum area in square meters
        max_area_sqm: Maximum area in square meters

    Returns:
        Filtered GeoDataFrame
    """
    try:
        # Calculate area in square meters (assuming CRS is in meters or convert to it)
        if buildings_gdf.crs and not buildings_gdf.crs.is_projected:
            # Convert to Web Mercator for area calculation
            buildings_gdf = buildings_gdf.to_crs("EPSG:3857")

        buildings_gdf['area_sqm'] = buildings_gdf.geometry.area

        # Filter by area
        filtered = buildings_gdf[
            (buildings_gdf['area_sqm'] >= min_area_sqm) &
            (buildings_gdf['area_sqm'] <= max_area_sqm)
        ]

        # Convert back to WGS84
        if filtered.crs != "EPSG:4326":
            filtered = filtered.to_crs("EPSG:4326")

        return filtered

    except Exception as e:
        st.error(f"Error filtering by size: {str(e)}")
        return buildings_gdf


def buildings_to_geojson(buildings_gdf):
    """
    Convert buildings GeoDataFrame to GeoJSON format.

    Args:
        buildings_gdf: GeoDataFrame of buildings

    Returns:
        GeoJSON string
    """
    try:
        if buildings_gdf.empty:
            return json.dumps({"type": "FeatureCollection", "features": []})

        # Ensure we're in WGS84
        if buildings_gdf.crs != "EPSG:4326":
            buildings_gdf = buildings_gdf.to_crs("EPSG:4326")

        # Convert to GeoJSON
        geojson_data = json.loads(buildings_gdf.to_json())

        return json.dumps(geojson_data)

    except Exception as e:
        st.error(f"Error converting to GeoJSON: {str(e)}")
        return json.dumps({"type": "FeatureCollection", "features": []})


def extract_buildings_from_map_view(bounds, zoom_level=19, min_area_sqm=10, max_area_sqm=10000):
    """
    Complete workflow to extract buildings from a map view.

    Args:
        bounds: Dictionary with '_southWest' and '_northEast' keys containing lat/lon
        zoom_level: Zoom level for imagery download
        min_area_sqm: Minimum building area in square meters
        max_area_sqm: Maximum building area in square meters

    Returns:
        Tuple of (building_count, avg_confidence, geojson_string)
    """
    try:
        # Extract bounding box from bounds
        bbox = (
            bounds['_southWest']['lng'],  # min_lon
            bounds['_southWest']['lat'],  # min_lat
            bounds['_northEast']['lng'],  # max_lon
            bounds['_northEast']['lat']   # max_lat
        )

        # Create filter geometry from bbox
        filter_geometry = box(*bbox)

        # Download satellite imagery
        image_path = download_satellite_imagery(bbox, zoom=zoom_level)
        if image_path is None:
            return 0, 0.0, json.dumps({"type": "FeatureCollection", "features": []})

        # Extract buildings using SAM2
        buildings_path = extract_buildings_sam2(image_path)
        if buildings_path is None:
            return 0, 0.0, json.dumps({"type": "FeatureCollection", "features": []})

        # Read and filter buildings
        buildings_gdf = gpd.read_file(buildings_path)

        # Filter by size
        buildings_gdf = filter_buildings_by_size(buildings_gdf, min_area_sqm, max_area_sqm)

        # Calculate statistics
        building_count = len(buildings_gdf)

        # SAM2 doesn't provide confidence scores like Google Open Buildings,
        # so we'll use a placeholder or calculate based on mask stability
        avg_confidence = 0.85  # Default confidence for SAM2 detections

        # Convert to GeoJSON
        geojson_string = buildings_to_geojson(buildings_gdf)

        # Clean up temporary files
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except:
                pass

        if buildings_path and os.path.exists(buildings_path):
            try:
                os.remove(buildings_path)
            except:
                pass

        return building_count, avg_confidence, geojson_string

    except Exception as e:
        st.error(f"Error in building extraction workflow: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return 0, 0.0, json.dumps({"type": "FeatureCollection", "features": []})
