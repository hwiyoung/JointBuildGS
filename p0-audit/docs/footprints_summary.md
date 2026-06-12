# T5 LoD2 Footprint Extraction

- Run ID: t5_footprints_20260612_130959
- Run directory: runs/t5_footprints_20260612_130959
- LoD2 source files: 690_5334.gml, 690_5336.gml
- CRS assertion: EPSG:25832 numeric bounds PASS
- Ground plan GPKG: data/work/footprints/lod2_ground_plan.gpkg
- Scene AOI GPKG: data/work/footprints/scene_aoi.gpkg
- Scene AOI intersecting buildings CSV: docs/scene_aoi_buildings.csv
- Buildings with usable LoD2 GroundSurface: 12,049
- Ground plan polygon parts: 12,049
- Buildings intersecting scene AOI: 199
- Ground plan bounds: x=[689943.800, 692065.860], y=[5333949.880, 5338012.713]
- Scene AOI bounds: x=[690791.740, 691154.650], y=[5335864.050, 5336353.850]
- Run config: runs/t5_footprints_20260612_130959/config.yaml
- Run versions: runs/t5_footprints_20260612_130959/versions.txt

## ogrinfo ground plan

```console
INFO: Open of `/workspace/data/work/footprints/lod2_ground_plan.gpkg'
      using driver `GPKG' successful.

Layer name: lod2_ground_plan
Geometry: Polygon
Feature Count: 12049
Extent: (689943.800000, 5333949.880000) - (692065.860000, 5338012.713000)
Layer SRS WKT:
PROJCRS["ETRS89 / UTM zone 32N",
    BASEGEOGCRS["ETRS89",
        ENSEMBLE["European Terrestrial Reference System 1989 ensemble",
            MEMBER["European Terrestrial Reference Frame 1989"],
            MEMBER["European Terrestrial Reference Frame 1990"],
            MEMBER["European Terrestrial Reference Frame 1991"],
            MEMBER["European Terrestrial Reference Frame 1992"],
            MEMBER["European Terrestrial Reference Frame 1993"],
            MEMBER["European Terrestrial Reference Frame 1994"],
            MEMBER["European Terrestrial Reference Frame 1996"],
            MEMBER["European Terrestrial Reference Frame 1997"],
            MEMBER["European Terrestrial Reference Frame 2000"],
            MEMBER["European Terrestrial Reference Frame 2005"],
            MEMBER["European Terrestrial Reference Frame 2014"],
            MEMBER["European Terrestrial Reference Frame 2020"],
            ELLIPSOID["GRS 1980",6378137,298.257222101,
                LENGTHUNIT["metre",1]],
            ENSEMBLEACCURACY[0.1]],
        PRIMEM["Greenwich",0,
            ANGLEUNIT["degree",0.0174532925199433]],
        ID["EPSG",4258]],
    CONVERSION["UTM zone 32N",
        METHOD["Transverse Mercator",
            ID["EPSG",9807]],
        PARAMETER["Latitude of natural origin",0,
            ANGLEUNIT["degree",0.0174532925199433],
            ID["EPSG",8801]],
        PARAMETER["Longitude of natural origin",9,
            ANGLEUNIT["degree",0.0174532925199433],
            ID["EPSG",8802]],
        PARAMETER["Scale factor at natural origin",0.9996,
            SCALEUNIT["unity",1],
            ID["EPSG",8805]],
        PARAMETER["False easting",500000,
            LENGTHUNIT["metre",1],
            ID["EPSG",8806]],
        PARAMETER["False northing",0,
            LENGTHUNIT["metre",1],
            ID["EPSG",8807]]],
    CS[Cartesian,2],
        AXIS["(E)",east,
            ORDER[1],
            LENGTHUNIT["metre",1]],
        AXIS["(N)",north,
            ORDER[2],
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Engineering survey, topographic mapping."],
        AREA["Europe between 6°E and 12°E: Austria; Denmark - onshore and offshore; Germany - onshore and offshore; Italy - onshore and offshore; Norway including Svalbard - onshore and offshore; Spain - offshore."],
        BBOX[36.53,6,84.01,12.01]],
    USAGE[
        SCOPE["Pan-European conformal mapping at scales larger than 1:500,000."],
        AREA["Europe between 6°E and 12°E and approximately 36°30'N to 84°N."],
        BBOX[36.53,6,84.01,12.01]],
    ID["EPSG",25832]]
Data axis to CRS axis mapping: 1,2
FID Column = fid
Geometry Column = geom
building_id: String (0.0)
source_file: String (0.0)
part_id: Integer (0.0)
area_m2: Real (0.0)
min_x: Real (0.0)
min_y: Real (0.0)
max_x: Real (0.0)
max_y: Real (0.0)
```

## ogrinfo scene AOI

```console
INFO: Open of `/workspace/data/work/footprints/scene_aoi.gpkg'
      using driver `GPKG' successful.

Layer name: scene_aoi
Geometry: Polygon
Feature Count: 1
Extent: (690791.740000, 5335864.050000) - (691154.650000, 5336353.850000)
Layer SRS WKT:
PROJCRS["ETRS89 / UTM zone 32N",
    BASEGEOGCRS["ETRS89",
        ENSEMBLE["European Terrestrial Reference System 1989 ensemble",
            MEMBER["European Terrestrial Reference Frame 1989"],
            MEMBER["European Terrestrial Reference Frame 1990"],
            MEMBER["European Terrestrial Reference Frame 1991"],
            MEMBER["European Terrestrial Reference Frame 1992"],
            MEMBER["European Terrestrial Reference Frame 1993"],
            MEMBER["European Terrestrial Reference Frame 1994"],
            MEMBER["European Terrestrial Reference Frame 1996"],
            MEMBER["European Terrestrial Reference Frame 1997"],
            MEMBER["European Terrestrial Reference Frame 2000"],
            MEMBER["European Terrestrial Reference Frame 2005"],
            MEMBER["European Terrestrial Reference Frame 2014"],
            MEMBER["European Terrestrial Reference Frame 2020"],
            ELLIPSOID["GRS 1980",6378137,298.257222101,
                LENGTHUNIT["metre",1]],
            ENSEMBLEACCURACY[0.1]],
        PRIMEM["Greenwich",0,
            ANGLEUNIT["degree",0.0174532925199433]],
        ID["EPSG",4258]],
    CONVERSION["UTM zone 32N",
        METHOD["Transverse Mercator",
            ID["EPSG",9807]],
        PARAMETER["Latitude of natural origin",0,
            ANGLEUNIT["degree",0.0174532925199433],
            ID["EPSG",8801]],
        PARAMETER["Longitude of natural origin",9,
            ANGLEUNIT["degree",0.0174532925199433],
            ID["EPSG",8802]],
        PARAMETER["Scale factor at natural origin",0.9996,
            SCALEUNIT["unity",1],
            ID["EPSG",8805]],
        PARAMETER["False easting",500000,
            LENGTHUNIT["metre",1],
            ID["EPSG",8806]],
        PARAMETER["False northing",0,
            LENGTHUNIT["metre",1],
            ID["EPSG",8807]]],
    CS[Cartesian,2],
        AXIS["(E)",east,
            ORDER[1],
            LENGTHUNIT["metre",1]],
        AXIS["(N)",north,
            ORDER[2],
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Engineering survey, topographic mapping."],
        AREA["Europe between 6°E and 12°E: Austria; Denmark - onshore and offshore; Germany - onshore and offshore; Italy - onshore and offshore; Norway including Svalbard - onshore and offshore; Spain - offshore."],
        BBOX[36.53,6,84.01,12.01]],
    USAGE[
        SCOPE["Pan-European conformal mapping at scales larger than 1:500,000."],
        AREA["Europe between 6°E and 12°E and approximately 36°30'N to 84°N."],
        BBOX[36.53,6,84.01,12.01]],
    ID["EPSG",25832]]
Data axis to CRS axis mapping: 1,2
FID Column = fid
Geometry Column = geom
name: String (0.0)
crs: String (0.0)
min_x: Real (0.0)
min_y: Real (0.0)
max_x: Real (0.0)
max_y: Real (0.0)
```
