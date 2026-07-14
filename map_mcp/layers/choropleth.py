

class ChoroplethLayer:

    def __init__(self):
        self.metadata = {
            "name": "choropleth",
            "description": "Displays geographic regions shaded according to a numeric value.",
            "data_type": "dict",
            "required_fields": {
                "geojson": "GeoJSON FeatureCollection",
                "value_field": "string"
            },
            "example_input": {
                "geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "name": "Ashanti",
                                "population": 5600000
                            },
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [-2.80, 6.85],
                                        [-2.65, 6.90],
                                        [-2.50, 6.80],
                                        [-2.40, 6.60],
                                        [-2.55, 6.45],
                                        [-2.80, 6.85]
                                    ]
                                ]
                            }
                        },
                        {
                            "type": "Feature",
                            "properties": {
                                "name": "Greater Accra",
                                "population": 5300000
                            },
                            "geometry": {
                                "type": "MultiPolygon",
                                "coordinates": [
                                    [
                                        [
                                            [120.0, -5.0],
                                            [121.0, -5.0],
                                            [121.0, -6.0],
                                            [120.0, -5.0]
                                        ]
                                    ],
                                    [
                                        [
                                            [130.0, -4.0],
                                            [131.0, -4.0],
                                            [131.0, -5.0],
                                            [130.0, -4.0]
                                        ]
                                    ]
                                ]
                            }
                        }
                    ]
                },
                "value_field": "population"
            }
        }


    def process(self, data: dict) -> dict:

        geojson = data.get("geojson")
        value_field = data.get("value_field")

        if geojson is None:
            raise ValueError("Missing 'geojson'.")

        if value_field is None:
            raise ValueError("Missing 'value_field'.")

        return {
            "type": "choropleth",
            "geojson": geojson,
            "value_field": value_field,
        }