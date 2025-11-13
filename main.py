import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import geojson
from shapely.geometry import shape
from pyproj import Transformer
from io import BytesIO
import json
from overture_buildings import (
    DEFAULT_FEATURE_LIMIT,
    fetch_buildings_from_overture,
)
from map_features import *

APP_TITLE = "Overture Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")

def setup_app():
    # st.title(APP_TITLE)
    st.sidebar.title("Overture Buildings Explorer")

def initialize_session_state():
    for key, default in {
        'map_data': None,
        'filtered_building_data': None,
        'building_count': 0,
        'imagery_dates': [],
        'selected_feature_name': None,
        'info_box_visible': False,
        'lat': 0,
        'lon': 0,
        'input_geometry': None,
        'bounds': None,
        'zoom': 0,
        'data_truncated': False,
        'feature_limit': 1000000,  # Very high limit - effectively unlimited
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

def process_uploaded_file(uploaded_file):
    try:
        geojson_data = geojson.load(uploaded_file)
        features = geojson_data['features']
        feature_names = [feature['properties'].get('name', f'Feature {i}') for i, feature in enumerate(features)]
        selected_feature_name = st.sidebar.selectbox("Select a feature to display", feature_names)

        if st.session_state.selected_feature_name != selected_feature_name:
            st.session_state.filtered_building_data = None
            st.session_state.filtered_building_geojson = None
            st.session_state.building_count = 0
            st.session_state.info_box_visible = False
            st.session_state.data_truncated = False
            st.session_state.feature_limit = DEFAULT_FEATURE_LIMIT

        st.session_state.selected_feature_name = selected_feature_name
        selected_feature = next((feature for feature in features if feature['properties'].get('name') == selected_feature_name), None)

        if selected_feature:
            display_selected_feature(selected_feature)

    except Exception as e:
        st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
        st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

def display_selected_feature(selected_feature):
    input_geometry = shape(selected_feature['geometry'])
    center_lat, center_lon = get_geometry_center(input_geometry)
    st.session_state.lat = center_lat
    st.session_state.lon = center_lon

    m = create_base_map(center_lat, center_lon)
    folium.GeoJson(selected_feature).add_to(m)
    Fullscreen(position="topright", title="Expand me", title_cancel="Exit me", force_separate_button=True).add_to(m)

    if st.session_state.filtered_building_data is not None:
        folium.GeoJson(st.session_state.filtered_building_data).add_to(m)

    st.session_state.map_data = st_folium(m, width=1200, height=800)#, returned_objects=[])
    # print(st.session_state.map_data)

    st.session_state.input_geometry = input_geometry

    # Update info box visibility whenever we display a feature
    # st.session_state.info_box_visible = True

def get_geometry_center(geometry):
    if geometry.geom_type == 'Point':
        return geometry.y, geometry.x
    else:
        centroid = geometry.centroid
        return centroid.y, centroid.x

def create_base_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.TileLayer(
        name='ArcGIS World Imagery',
        control=True,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    return m

def download_and_process_building_data(input_geometry):
    if input_geometry is None:
        st.sidebar.warning("Please select a feature before fetching building data.")
        return

    with st.sidebar.status("Fetching building data from Overture Maps...", expanded=True) as status:
        message_placeholder = st.empty()
        progress_bar = st.progress(0)

        def update_progress(message, progress):
            message_placeholder.write(message)
            progress_bar.progress(progress)

        try:
            result = fetch_buildings_from_overture(
                input_geometry,
                limit=st.session_state.feature_limit,
                progress_callback=update_progress
            )

            st.session_state.building_count = result.building_count
            st.session_state.filtered_building_data = result.geojson
            st.session_state.filtered_building_geojson = json.dumps(result.geojson, separators=(',', ':'))
            st.session_state.info_box_visible = True
            st.session_state.data_truncated = result.truncated
            st.session_state.feature_limit = result.limit

            status.update(label="✓ Data fetched successfully!", state="complete", expanded=False)

        except Exception as e:
            progress_bar.empty()
            message_placeholder.empty()
            status.update(label="✗ Failed to fetch data", state="error", expanded=True)
            st.error("Unable to fetch building data from Overture Maps.")
            st.error(str(e))
            return

    st.rerun()

def display_fixed_info_box():
    with st.sidebar.expander("Building Data Summary", expanded=True):
        st.metric(label="Location", value=st.session_state.selected_feature_name, label_visibility="hidden")
        st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")
        st.metric(label="Total buildings", value=f"{st.session_state.building_count}")

        if st.session_state.data_truncated:
            st.warning(
                "The number of buildings exceeds the display limit. Only the first "
                f"{st.session_state.feature_limit} features are shown."
            )

        if hasattr(st.session_state, 'filtered_building_geojson') and st.session_state.filtered_building_geojson:
            geojson_bytes = BytesIO(st.session_state.filtered_building_geojson.encode("utf-8"))
            st.download_button(
                label="Download GeoJSON",
                data=geojson_bytes,
                file_name="overture_buildings.geojson",
                mime="application/geo+json"
            )

    if st.session_state.filtered_building_data:
        display_building_attributes()


def display_building_attributes():
    with st.sidebar.expander("Building Attributes Summary", expanded=False):
        features = st.session_state.filtered_building_data['features']

        if features:
            heights = [f['properties'].get('height') for f in features if f['properties'].get('height')]
            floors = [f['properties'].get('num_floors') for f in features if f['properties'].get('num_floors')]
            classes = [f['properties'].get('class') for f in features if f['properties'].get('class')]
            sources = []
            for f in features:
                props = f['properties']
                if props.get('sources') and isinstance(props['sources'], list) and props['sources']:
                    dataset = props['sources'][0].get('dataset', 'Unknown')
                    sources.append(dataset)

            if heights:
                avg_height = sum(heights) / len(heights)
                min_height = min(heights)
                max_height = max(heights)
                st.write(f"🏢 **Height** ({len(heights)} buildings)")
                st.write(f"   Avg: {avg_height:.1f}m | Min: {min_height:.1f}m | Max: {max_height:.1f}m")

            if floors:
                avg_floors = sum(floors) / len(floors)
                min_floors = min(floors)
                max_floors = max(floors)
                st.write(f"📊 **Floors** ({len(floors)} buildings)")
                st.write(f"   Avg: {avg_floors:.1f} | Min: {min_floors} | Max: {max_floors}")

            if classes:
                class_counts = {}
                for c in classes:
                    class_counts[c] = class_counts.get(c, 0) + 1
                st.write(f"🏗️ **Building Classes** ({len(classes)} classified)")
                for cls, count in sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    st.write(f"   {cls}: {count}")

            if sources:
                source_counts = {}
                for s in sources:
                    source_counts[s] = source_counts.get(s, 0) + 1
                st.write(f"📚 **Data Sources**")
                for src, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
                    st.write(f"   {src}: {count} buildings")


def main():
    setup_app()

    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    initialize_session_state()

    if uploaded_file:
        process_uploaded_file(uploaded_file)
        # get imagery dates
        bounds = st.session_state.map_data['bounds']
        # print(bounds)
        zoom_level = st.session_state.map_data['zoom']
        if zoom_level >= 12 and bounds:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            sw_x, sw_y = transformer.transform(bounds['_southWest']['lng'], bounds['_southWest']['lat'])
            ne_x, ne_y = transformer.transform(bounds['_northEast']['lng'], bounds['_northEast']['lat'])
            # print(sw_x, sw_y, ne_x, ne_y)

            dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)
            if dates:
                # change to str
                dates = ", ".join(dates)
                # print(dates)
                st.session_state.imagery_dates = dates
                # write
                st.sidebar.write(f"Imagery dates: {dates}")
        else:
            st.session_state.imagery_dates = f"Curent zoom level: {zoom_level} - Imagery dates are only available at zoom level 12 or higher."
            # write
        #st.sidebar.write(st.session_state.imagery_dates)

        if st.sidebar.button("Fetch Overture Buildings", key="download_building_button"):
            download_and_process_building_data(st.session_state.input_geometry)
            
        if st.session_state.info_box_visible:
            display_fixed_info_box()
    
    # Display imagery dates below the map
    

if __name__ == "__main__":
    main()
