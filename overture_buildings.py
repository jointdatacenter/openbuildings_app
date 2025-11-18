"""Utility functions for working with the Overture Maps Buildings dataset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple, Optional
import json
import hashlib
import streamlit as st

from overturemaps import record_batch_reader
from shapely.geometry import shape as shapely_shape
import pyarrow as pa

DEFAULT_FEATURE_LIMIT = 50000  # Increased to handle larger areas


def _bbox_to_cache_key(bbox: Tuple[float, float, float, float], limit: int) -> str:
    """Generate a cache key from bounding box and limit."""
    bbox_str = f"{bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f},{limit}"
    return hashlib.md5(bbox_str.encode()).hexdigest()


@dataclass
class BuildingFetchResult:
    """Container for the results returned from Overture Maps."""

    geojson: Dict[str, Any]
    building_count: int
    truncated: bool
    limit: int


def _parse_geometry_from_wkb(wkb_bytes) -> Dict[str, Any]:
    """Convert WKB geometry to GeoJSON."""
    try:
        from shapely import wkb
        geom = wkb.loads(bytes(wkb_bytes))
        return json.loads(json.dumps(geom.__geo_interface__))
    except Exception as e:
        print(f"[Overture] Warning: Failed to parse geometry: {e}")
        return None


def _is_valid_value(value) -> bool:
    """Check if value is valid (not None, not NaN)."""
    import pandas as pd
    if value is None:
        return False
    if pd.isna(value):
        return False
    return True


def _convert_to_python_type(value):
    """Convert numpy/pandas types to Python native types."""
    import numpy as np

    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    elif isinstance(value, np.ndarray):
        return value.tolist()
    elif isinstance(value, (list, tuple)):
        return [_convert_to_python_type(item) for item in value]
    elif isinstance(value, dict):
        return {k: _convert_to_python_type(v) for k, v in value.items()}
    else:
        return value


def _extract_properties(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant properties from Overture building record."""
    properties = {}

    try:
        if 'id' in record and _is_valid_value(record['id']):
            properties['id'] = str(record['id'])
    except:
        pass

    try:
        if 'height' in record and _is_valid_value(record['height']):
            properties['height'] = float(_convert_to_python_type(record['height']))
    except:
        pass

    try:
        if 'num_floors' in record and _is_valid_value(record['num_floors']):
            properties['num_floors'] = int(_convert_to_python_type(record['num_floors']))
    except:
        pass

    try:
        if 'class' in record and _is_valid_value(record['class']):
            properties['class'] = str(record['class'])
    except:
        pass

    try:
        if 'sources' in record and _is_valid_value(record['sources']):
            sources = record['sources']
            if isinstance(sources, str):
                sources = json.loads(sources)
            sources = _convert_to_python_type(sources)
            if sources:
                properties['sources'] = sources
    except:
        pass

    return properties


def _to_feature_collection(batches, limit: int) -> Dict[str, Any]:
    """Convert PyArrow record batches to GeoJSON FeatureCollection."""
    features = []
    count = 0

    for batch in batches:
        if count >= limit:
            break

        df = batch.to_pandas()

        for _, row in df.iterrows():
            if count >= limit:
                break

            try:
                geometry = _parse_geometry_from_wkb(row['geometry'])
                if not geometry:
                    continue

                centroid = shapely_shape(geometry).centroid

                properties = _extract_properties(row.to_dict())
                properties['latitude'] = centroid.y
                properties['longitude'] = centroid.x

                features.append({
                    'type': 'Feature',
                    'geometry': geometry,
                    'properties': properties,
                })

                count += 1

                if count % 500 == 0:
                    print(f"[Overture] Processed {count} buildings...")

            except Exception as e:
                print(f"[Overture] Warning: Failed to process feature: {e}")
                continue

    return {
        'type': 'FeatureCollection',
        'features': features,
    }


@st.cache_data(ttl=3600 * 24 * 7, show_spinner=False)  # Cache for 7 days
def _fetch_buildings_cached(bbox: Tuple[float, float, float, float], limit: int) -> BuildingFetchResult:
    """Cached version of building fetch that doesn't include progress callbacks.

    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
        limit: Maximum number of buildings to fetch
    """
    print(f"\n[Overture] Cache miss - fetching data for bbox: {bbox}")
    print(f"[Overture] Using Overture Python SDK with optimized streaming...")

    try:
        reader = record_batch_reader(
            overture_type="building",
            bbox=bbox
        )

        if reader is None:
            raise RuntimeError("Overture SDK returned None - no data available for this region")

        print("[Overture] Streaming building data from S3...")
        print("[Overture] This may take 2-10 minutes for the first query...")

        batches = []
        total_count = 0
        batch_count = 0

        for i, batch in enumerate(reader):
            batch_size = len(batch)
            total_count += batch_size
            batch_count += 1
            batches.append(batch)

            if i % 2 == 0:
                print(f"[Overture] Batch {batch_count}: Fetched {total_count} buildings so far...")

            if total_count >= limit:
                print(f"[Overture] Reached limit of {limit}, stopping...")
                break

        print(f"[Overture] Download complete! Total: {total_count} buildings")
        print("[Overture] Converting to GeoJSON...")

        geojson = _to_feature_collection(batches, limit)
        building_count = len(geojson['features'])
        truncated = total_count > limit

        print(f"[Overture] Conversion complete! Generated {building_count} features")

        return BuildingFetchResult(
            geojson=geojson,
            building_count=building_count,
            truncated=truncated,
            limit=limit,
        )

    except Exception as e:
        print(f"[Overture] ERROR: {str(e)}")
        raise RuntimeError(f"Failed to fetch buildings from Overture Maps: {str(e)}") from e


def fetch_buildings_from_overture(input_geometry, limit: int = DEFAULT_FEATURE_LIMIT, progress_callback=None) -> BuildingFetchResult:
    """Fetch building footprints from Overture Maps for the provided geometry.

    This function uses caching to avoid re-fetching the same data. Progress updates
    are simulated when data is retrieved from cache.

    Args:
        input_geometry: Shapely geometry defining the area of interest
        limit: Maximum number of buildings to fetch
        progress_callback: Optional callback function(message, progress) for UI updates
    """
    bounds = input_geometry.bounds
    min_lon, min_lat, max_lon, max_lat = bounds
    bbox_tuple = (min_lon, min_lat, max_lon, max_lat)

    cache_key = _bbox_to_cache_key(bbox_tuple, limit)
    print(f"\n[Overture] Cache key: {cache_key}")
    print(f"[Overture] Starting query for bounds: {bbox_tuple}")

    if progress_callback:
        progress_callback("🔍 Checking cache...", 0)

    try:
        # Check if this is a cache hit by looking at Streamlit's cache
        # If cached, provide simulated progress updates for better UX
        if progress_callback:
            progress_callback("📦 Fetching building data...", 10)

        result = _fetch_buildings_cached(bbox_tuple, limit)

        # Simulate progress for cached results to provide consistent UX
        if progress_callback:
            progress_callback("🏗️ Processing data...", 70)
            progress_callback("✅ Complete!", 100)

        return result

    except Exception as e:
        print(f"[Overture] ERROR: {str(e)}")
        if progress_callback:
            progress_callback(f"❌ Error: {str(e)}", 0)
        raise
