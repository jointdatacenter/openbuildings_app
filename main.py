import os
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
from pyproj import Transformer
from io import BytesIO
import json
from building_extractor import extract_buildings_from_map_view
from map_features import get_imagery_dates

data_dir = './data/'
APP_TITLE = "Building Extractor from Satellite Imagery"
st.set_page_config(page_title=APP_TITLE, layout="wide")


def setup_app():
    st.sidebar.title("Building Extractor")
    st.sidebar.markdown("""
    This app extracts buildings from satellite imagery using AI (SAM2).

    **How to use:**
    1. Navigate to your area of interest on the map
    2. Zoom in to at least level 17 for best results
    3. Click "Extract Buildings" to detect buildings in the current view
    """)


def initialize_session_state():
    for key, default in {
        'map_data': None,
        'extracted_buildings': None,
        'building_count': 0,
        'avg_confidence': 0.0,
        'imagery_dates': [],
        'info_box_visible': False,
        'lat': 40.7128,  # Default to New York City
        'lon': -74.0060,
        'zoom': 17,
        'progress_message': "",
        'bounds': None,
        'processing': False,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default


def create_base_map(lat, lon, zoom=17):
    """Create a base map with satellite imagery."""
    m = folium.Map(location=[lat, lon], zoom_start=zoom)
    folium.TileLayer(
        name='ArcGIS World Imagery',
        control=True,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True
    ).add_to(m)
    return m


def display_map():
    """Display the interactive map."""
    m = create_base_map(st.session_state.lat, st.session_state.lon, st.session_state.zoom)

    # Add extracted buildings if available
    if st.session_state.extracted_buildings is not None:
        try:
            buildings_geojson = json.loads(st.session_state.extracted_buildings)
            folium.GeoJson(
                buildings_geojson,
                name='Extracted Buildings',
                style_function=lambda x: {
                    'fillColor': '#ff7800',
                    'color': '#ff7800',
                    'weight': 2,
                    'fillOpacity': 0.4
                }
            ).add_to(m)
        except Exception as e:
            st.error(f"Error displaying buildings: {str(e)}")

    st.session_state.map_data = st_folium(m, width=1200, height=800, key="main_map")

    # Update location and zoom from map interaction
    if st.session_state.map_data:
        if 'center' in st.session_state.map_data and st.session_state.map_data['center']:
            st.session_state.lat = st.session_state.map_data['center']['lat']
            st.session_state.lon = st.session_state.map_data['center']['lng']

        if 'zoom' in st.session_state.map_data and st.session_state.map_data['zoom']:
            st.session_state.zoom = st.session_state.map_data['zoom']

        if 'bounds' in st.session_state.map_data and st.session_state.map_data['bounds']:
            st.session_state.bounds = st.session_state.map_data['bounds']


def extract_buildings():
    """Extract buildings from the current map view."""
    if st.session_state.bounds is None:
        st.sidebar.error("Please interact with the map first to set the view bounds")
        return

    if st.session_state.zoom < 17:
        st.sidebar.warning(
            f"Current zoom level: {st.session_state.zoom}. "
            "Please zoom in to at least level 17 for accurate building extraction."
        )
        return

    st.session_state.processing = True

    try:
        # Get parameters from sidebar
        zoom_level = st.sidebar.slider(
            "Imagery Zoom Level",
            min_value=17,
            max_value=20,
            value=19,
            help="Higher zoom = more detail but slower processing"
        )

        min_area = st.sidebar.number_input(
            "Minimum Building Area (sq m)",
            min_value=5,
            max_value=100,
            value=10,
            help="Filter out buildings smaller than this"
        )

        max_area = st.sidebar.number_input(
            "Maximum Building Area (sq m)",
            min_value=100,
            max_value=50000,
            value=10000,
            help="Filter out buildings larger than this"
        )

        # Extract buildings
        building_count, avg_confidence, geojson_string = extract_buildings_from_map_view(
            st.session_state.bounds,
            zoom_level=zoom_level,
            min_area_sqm=min_area,
            max_area_sqm=max_area
        )

        # Update session state
        st.session_state.building_count = building_count
        st.session_state.avg_confidence = avg_confidence
        st.session_state.extracted_buildings = geojson_string
        st.session_state.info_box_visible = True
        st.session_state.processing = False

        st.success(f"Extraction complete! Found {building_count} buildings.")
        st.rerun()

    except Exception as e:
        st.error(f"Error during extraction: {str(e)}")
        st.session_state.processing = False


def display_info_box():
    """Display information about extracted buildings."""
    with st.sidebar.expander("Extraction Results", expanded=True):
        st.metric(
            label="Location",
            value=f"{st.session_state.lat:.6f}, {st.session_state.lon:.6f}"
        )
        st.metric(
            label="Total Buildings",
            value=st.session_state.building_count
        )
        st.metric(
            label="Avg Confidence",
            value=f"{st.session_state.avg_confidence:.2f}"
        )

        if st.session_state.extracted_buildings:
            geojson_bytes = BytesIO(st.session_state.extracted_buildings.encode("utf-8"))
            st.download_button(
                label="Download GeoJSON",
                data=geojson_bytes,
                file_name="extracted_buildings.geojson",
                mime="application/geo+json"
            )


def display_imagery_dates():
    """Display imagery dates for the current view."""
    if st.session_state.map_data is None:
        return

    bounds = st.session_state.map_data.get('bounds')
    zoom_level = st.session_state.map_data.get('zoom', 0)

    if zoom_level >= 12 and bounds:
        try:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            sw_x, sw_y = transformer.transform(
                bounds['_southWest']['lng'],
                bounds['_southWest']['lat']
            )
            ne_x, ne_y = transformer.transform(
                bounds['_northEast']['lng'],
                bounds['_northEast']['lat']
            )

            dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)
            if dates:
                dates_str = ", ".join(dates)
                st.sidebar.write(f"**Imagery dates:** {dates_str}")
        except Exception as e:
            st.sidebar.write(f"Could not fetch imagery dates: {str(e)}")
    else:
        st.sidebar.write(f"*Zoom to level 12+ to see imagery dates (current: {zoom_level})*")


def main():
    setup_app()
    initialize_session_state()

    # Display the map
    display_map()

    # Display imagery dates
    display_imagery_dates()

    # Add extraction controls
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Extraction Settings")

    # Only show extraction button if not processing
    if not st.session_state.processing:
        if st.sidebar.button("Extract Buildings", type="primary", use_container_width=True):
            extract_buildings()
    else:
        st.sidebar.info("Processing... Please wait.")

    # Display info box if buildings have been extracted
    if st.session_state.info_box_visible:
        display_info_box()

    # Add a button to clear results
    if st.session_state.extracted_buildings is not None:
        if st.sidebar.button("Clear Results", use_container_width=True):
            st.session_state.extracted_buildings = None
            st.session_state.building_count = 0
            st.session_state.avg_confidence = 0.0
            st.session_state.info_box_visible = False
            st.rerun()


if __name__ == "__main__":
    main()
