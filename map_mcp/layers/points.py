

class PointsLayer:

    def __init__(self):
        self.metadata = {
            "name": "points",
            "description": "Displays one or more geographic locations as interactive markers.",
            "data_type": "list[dict]",
            "required_fields": {
                "latitude": "float",
                "longitude": "float",
                "label": "string",
            },
            "example_input": [
                {"latitude": 5.6037, "longitude": -0.1870, "label": "Accra"},
            ],
        }
    
    def process(self, data: list[dict]) -> dict:
        points = []
        for row in data:
            lat = row.get("latitude", row.get("lat"))
            lng = row.get("longitude", row.get("lng"))
            if lat is None or lng is None:
                raise ValueError(f"Point missing latitude/longitude: {row}")
            points.append({
                "lat": float(lat),
                "lng": float(lng),
                "label": row.get("label", ""),
                "value": row.get("value"),
            })
        return {"type": "points", "points": points}