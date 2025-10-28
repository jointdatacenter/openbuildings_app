# References

[https://docs.streamlit.io/develop/tutorials/databases/gcs](https://docs.streamlit.io/develop/tutorials/databases/gcs)

[https://blog.christianperone.com/2015/08/googles-s2-geometry-on-the-sphere-cells-and-hilbert-curve/](https://blog.christianperone.com/2015/08/googles-s2-geometry-on-the-sphere-cells-and-hilbert-curve/)

https://open.gishub.org/open-buildings/examples/download_buildings/

## Google Earth Engine configuration

This application now queries building footprints directly from the
[Google Earth Engine Open Buildings dataset](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings_v3).
To authenticate against Earth Engine in a non-interactive environment set the following
environment variables before starting Streamlit:

```
EE_SERVICE_ACCOUNT="service-account@project.iam.gserviceaccount.com"
EE_PRIVATE_KEY="$(cat service-account-key.json)"
```

Alternatively, run `ee.Authenticate()` locally to generate persistent credentials that the
application can reuse via `ee.Initialize()`.