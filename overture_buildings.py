"""Utility functions for working with the Overture Maps Buildings dataset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
import json

from overturemaps import record_batch_reader
from shapely.geometry import shape as shapely_shape
import pyarrow as pa

DEFAULT_FEATURE_LIMIT = 50000  # Increased to handle larger areas


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
    """Extract all available properties from Overture building record."""
    properties = {}

    fields_to_extract = [
        ('id', str),
        ('height', float),
        ('num_floors', int),
        ('class', str),
        ('subtype', str),
        ('names', None),
        ('level', int),
        ('has_parts', bool),
        ('is_underground', bool),
        ('facade_color', str),
        ('facade_material', str),
        ('roof_material', str),
        ('roof_shape', str),
        ('roof_direction', float),
        ('roof_orientation', str),
        ('roof_color', str),
        ('eave_height', float),
        ('min_height', float),
        ('min_floor', int),
        ('sources', None),
    ]

    for field_name, field_type in fields_to_extract:
        try:
            if field_name in record and _is_valid_value(record[field_name]):
                value = record[field_name]

                if field_name == 'sources':
                    if isinstance(value, str):
                        value = json.loads(value)
                    value = _convert_to_python_type(value)
                    if value:
                        properties[field_name] = value
                elif field_name == 'names':
                    if isinstance(value, str):
                        value = json.loads(value)
                    value = _convert_to_python_type(value)
                    if value:
                        properties[field_name] = value
                elif field_type == int:
                    properties[field_name] = int(_convert_to_python_type(value))
                elif field_type == float:
                    properties[field_name] = float(_convert_to_python_type(value))
                elif field_type == bool:
                    properties[field_name] = bool(_convert_to_python_type(value))
                elif field_type == str:
                    properties[field_name] = str(value)
                else:
                    properties[field_name] = _convert_to_python_type(value)
        except:
            pass

    for key, value in record.items():
        if key not in properties and key != 'geometry' and _is_valid_value(value):
            try:
                properties[key] = _convert_to_python_type(value)
            except:
                pass

    return properties


def _to_feature_collection(batches, limit: int, input_geometry=None) -> Dict[str, Any]:
    """Convert PyArrow record batches to GeoJSON FeatureCollection.

    Args:
        batches: PyArrow record batches
        limit: Maximum number of features to process
        input_geometry: Optional Shapely geometry to filter buildings that intersect
    """
    features = []
    count = 0
    filtered_count = 0

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

                building_shape = shapely_shape(geometry)

                if input_geometry is not None:
                    if not building_shape.intersects(input_geometry):
                        filtered_count += 1
                        continue

                centroid = building_shape.centroid

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
                    print(f"[Overture] Processed {count} buildings (filtered out {filtered_count})...")

            except Exception as e:
                print(f"[Overture] Warning: Failed to process feature: {e}")
                continue

    if filtered_count > 0:
        print(f"[Overture] Filtered out {filtered_count} buildings outside polygon boundary")

    return {
        'type': 'FeatureCollection',
        'features': features,
    }


def fetch_buildings_from_overture(input_geometry, limit: int = DEFAULT_FEATURE_LIMIT, progress_callback=None) -> BuildingFetchResult:
    """Fetch building footprints from Overture Maps for the provided geometry.

    Args:
        input_geometry: Shapely geometry defining the area of interest
        limit: Maximum number of buildings to fetch
        progress_callback: Optional callback function(message, progress) for UI updates
    """

    bounds = input_geometry.bounds
    min_lon, min_lat, max_lon, max_lat = bounds

    bbox_tuple = (min_lon, min_lat, max_lon, max_lat)

    print(f"\n[Overture] Starting query for bounds: {bbox_tuple}")
    print(f"[Overture] Using Overture Python SDK with optimized streaming...")

    if progress_callback:
        progress_callback("🔍 Initializing query...", 0)

    try:
        reader = record_batch_reader(
            overture_type="building",
            bbox=bbox_tuple,
            release="2025-11-19.0"
        )

        if reader is None:
            raise RuntimeError("Overture SDK returned None - no data available for this region")

        print("[Overture] Streaming building data from S3...")
        print("[Overture] This may take 2-10 minutes for the first query...")

        if progress_callback:
            progress_callback("📦 Connecting to S3 and starting stream...", 5)

        batches = []
        total_count = 0
        batch_count = 0

        for i, batch in enumerate(reader):
            batch_size = len(batch)
            total_count += batch_size
            batch_count += 1
            batches.append(batch)

            if i == 0 and progress_callback:
                progress_callback(f"📦 First batch received! Streaming data from S3...", 10)

            if i % 2 == 0:
                print(f"[Overture] Batch {batch_count}: Fetched {total_count} buildings so far...")
                if progress_callback:
                    progress = min(10 + int((total_count / max(limit, 1000)) * 50), 60)
                    progress_callback(f"📦 Downloading batch {batch_count}... {total_count} buildings fetched", progress)

            if total_count >= limit:
                print(f"[Overture] Reached limit of {limit}, stopping...")
                break

        print(f"[Overture] Download complete! Total: {total_count} buildings")

        if progress_callback:
            progress_callback(f"✅ Download complete! Processing {total_count} buildings...", 65)

        print("[Overture] Converting to GeoJSON and filtering to polygon boundary...")

        geojson = _to_feature_collection(batches, limit, input_geometry)

        if progress_callback:
            progress_callback("🏗️ Finalizing GeoJSON conversion...", 90)

        building_count = len(geojson['features'])
        truncated = total_count > limit

        print(f"[Overture] Conversion complete! Generated {building_count} features")

        if progress_callback:
            progress_callback("✅ Complete!", 100)

        return BuildingFetchResult(
            geojson=geojson,
            building_count=building_count,
            truncated=truncated,
            limit=limit,
        )

    except Exception as e:
        print(f"[Overture] ERROR: {str(e)}")
        if progress_callback:
            progress_callback(f"❌ Error: {str(e)}", 0)
        raise RuntimeError(f"Failed to fetch buildings from Overture Maps: {str(e)}") from e
