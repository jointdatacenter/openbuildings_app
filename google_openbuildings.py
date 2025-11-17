from typing import List, Optional
import geopandas as gpd
import shapely
import pandas as pd
import s2sphere as s2
import streamlit as st
import os
import fsspec
from shapely.wkt import loads
from io import StringIO
import json
import psutil
import gc
import requests

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

BUILDING_DOWNLOAD_PATH = 'gs://open-buildings-data/v3/polygons_s2_level_6_gzip_no_header'
BUILDING_DOWNLOAD_URL = 'https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_6_gzip_no_header'

def wkt_to_s2(your_own_wkt_polygon: str) -> List[str]:
    """Takes a WKT polygon, converts to a geopandas GeoDataFrame, and returns S2 covering tokens."""

    # Convert WKT polygon to GeoDataFrame
    region_df = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries.from_wkt([your_own_wkt_polygon]),
        crs='EPSG:4326'
    )
    
    # Validate the geometry type
    if not isinstance(region_df.iloc[0].geometry, (shapely.geometry.polygon.Polygon, shapely.geometry.multipolygon.MultiPolygon)):
        raise ValueError("`your_own_wkt_polygon` must be a POLYGON or MULTIPOLYGON.")
    
    # Get bounds of the region
    region_bounds = region_df.iloc[0].geometry.bounds
    
    # Create S2LatLngRect for covering using s2sphere
    sw_latlng = s2.LatLng.from_degrees(region_bounds[1], region_bounds[0])  # sw corner
    ne_latlng = s2.LatLng.from_degrees(region_bounds[3], region_bounds[2])  # ne corner
    
    # Create covering using s2sphere
    region_coverer = s2.RegionCoverer()
    region_coverer.max_level = 6
    region_coverer.min_level = 6
    region_coverer.max_cells = 1000000
    
    # Create a rect region
    rect = s2.LatLngRect.from_point_pair(sw_latlng, ne_latlng)
    
    # Get covering
    covering = region_coverer.get_covering(rect)
    tokens = [cell.to_token() for cell in covering]
    print(tokens)
    # Return the covering tokens
    return tokens

########
import os
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
from typing import Optional
from st_files_connection import FilesConnection

def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
    """
    Downloads data from Google Cloud Storage based on S2 code for building polygons.
    Args:
        s2_code (str): S2 code to download building polygons for.
        data_dir (str): Directory to save the downloaded data.
    Returns:
        Optional[str]: Path to gzipped CSV file if successful, None otherwise.
    """
    if not isinstance(s2_code, str) or not isinstance(data_dir, str):
        st.error("Both s2_code and data_dir must be strings")
        return None
    
    print(s2_code)

    # Define output path
    output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')
    print(output_path)
    # Ensure data directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    # st.sidebar.write(f"Downloading data to: {output_path}")
    
    # Check if the file already exists
    if os.path.exists(output_path):
        print(f"File already exists: {output_path}")
        return output_path

    try:
        # Construct the HTTP URL for public GCS data
        download_url = f'{BUILDING_DOWNLOAD_URL}/{s2_code}_buildings.csv.gz'
        print(download_url)

        # Initialize progress bar
        status_text = st.sidebar.empty()
        progress_bar = st.sidebar.progress(0)

        # Download with streaming
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Get total file size
        total_size = int(response.headers.get('content-length', 0))

        # Download the file in chunks
        with open(output_path, 'wb') as out:
            bytes_downloaded = 0
            chunk_size = 65536  # 64KB chunks

            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    out.write(chunk)
                    bytes_downloaded += len(chunk)

                    if total_size > 0:
                        progress = min(1.0, bytes_downloaded / total_size)
                        progress_bar.progress(progress)
                        status_text.write(f"Downloaded {bytes_downloaded/1e6:.2f} MB out of {total_size/1e6:.2f} MB")
                    else:
                        status_text.write(f"Downloaded {bytes_downloaded/1e6:.2f} MB")

        # Clear status elements
        status_text.empty()
        progress_bar.empty()

        # Verify the downloaded file exists and is not empty
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            st.success(f"Download completed: {output_path}")
            return str(output_path)
        else:
            st.error("Downloaded file is empty or does not exist")
            return None
            
    except Exception as e:
        st.error(f"Error during download: {str(e)}")
        # Clean up any partial file if it exists
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                st.write(f"Partial file removed: {output_path}")
            except Exception as cleanup_error:
                st.error(f"Error cleaning up partial file: {str(cleanup_error)}")
        return None

def load_and_filter_gob_data_streaming(gob_filepath, input_geometry):
    """
    Memory-efficient streaming processing of GOB data with chunked reading.
    """
    try:
        header = ['latitude', 'longitude', 'area_in_meters', 'confidence', 'geometry', 'full_plus_code']
        
        # Initialize counters and accumulators
        building_count = 0
        confidence_sum = 0
        filtered_features = []
        
        # Process CSV in chunks to reduce memory usage
        chunk_size = 10000  # Process 10k records at a time
        
        for chunk in pd.read_csv(gob_filepath, chunksize=chunk_size):
            chunk.columns = header
            
            # Convert geometry strings to shapely objects for this chunk only
            chunk['geometry'] = chunk['geometry'].apply(loads)
            chunk_gdf = gpd.GeoDataFrame(chunk, crs='EPSG:4326')
            
            # Filter intersecting geometries
            filtered_chunk = chunk_gdf[chunk_gdf.intersects(input_geometry)]
            
            if not filtered_chunk.empty:
                # Update counters
                building_count += len(filtered_chunk)
                confidence_sum += filtered_chunk['confidence'].sum()
                
                # Convert to GeoJSON features and append
                for _, row in filtered_chunk.iterrows():
                    feature = {
                        "type": "Feature",
                        "geometry": row['geometry'].__geo_interface__,
                        "properties": {
                            "latitude": row['latitude'],
                            "longitude": row['longitude'],
                            "area_in_meters": row['area_in_meters'],
                            "confidence": row['confidence'],
                            "full_plus_code": row['full_plus_code']
                        }
                    }
                    filtered_features.append(feature)
            
            # Clear chunk from memory
            del chunk_gdf, filtered_chunk
            gc.collect()  # Force garbage collection
        
        # Calculate average confidence
        avg_confidence = confidence_sum / building_count if building_count > 0 else 0
        
        # Create final GeoJSON structure
        geojson_data = {
            "type": "FeatureCollection",
            "features": filtered_features
        }
        
        # Store only essential data in session state
        st.session_state.building_count = building_count
        st.session_state.avg_confidence = avg_confidence
        st.session_state.filtered_gob_data = json.dumps(geojson_data)
        st.session_state.info_box_visible = True
        
        # Prepare compressed GeoJSON for download
        st.session_state.filtered_gob_geojson = json.dumps(geojson_data, separators=(',', ':'))
        
        # Log memory usage
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"Memory usage after processing: {memory_mb:.1f} MB")
        
        st.rerun()
    except Exception as e:
        st.error(f"Error processing GOB data: {str(e)}")
        print(e)