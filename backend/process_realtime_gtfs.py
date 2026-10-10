import os
import requests
from google.transit import gtfs_realtime_pb2
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

def main():
    print("Starting GTFS-Realtime Fetch...")
    
    # 1. Connect to Database
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set!")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(db_url)
    
    # 2. Download the GTFS-Realtime Protobuf feed
    url = "https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-kl"
    response = requests.get(url)
    response.raise_for_status()
    
    # 3. Parse the Protobuf Binary Data
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    
    positions = []
    for entity in feed.entity:
        if entity.HasField('vehicle'):
            v = entity.vehicle
            
            # Extract timestamp safely (Fallback to current UTC if missing)
            if v.timestamp:
                ts = datetime.fromtimestamp(v.timestamp, tz=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)
                
            positions.append({
                "vehicle_id": v.vehicle.id,
                "trip_id": v.trip.trip_id,
                "route_id": v.trip.route_id,
                "lat": v.position.latitude,
                "lon": v.position.longitude,
                "status": str(v.current_status),
                "timestamp": ts
            })
            
    if not positions:
        print("No vehicle positions found currently.")
        return
        
    print(f"Parsed {len(positions)} live buses. Updating Supabase...")
    
    # 4. Upsert Data (Update coordinates if bus exists, insert if new)
    upsert_query = text("""
        INSERT INTO vehicle_positions (vehicle_id, trip_id, route_id, latitude, longitude, geom, current_status, timestamp, updated_at)
        VALUES (:vehicle_id, :trip_id, :route_id, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :status, :timestamp, NOW())
        ON CONFLICT (vehicle_id) DO UPDATE SET
            trip_id = EXCLUDED.trip_id,
            route_id = EXCLUDED.route_id,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            geom = EXCLUDED.geom,
            current_status = EXCLUDED.current_status,
            timestamp = EXCLUDED.timestamp,
            updated_at = NOW();
    """)
    
    with engine.begin() as conn:
        conn.execute(upsert_query, positions)
        
    print("Realtime database update completed successfully!")

if __name__ == "__main__":
    main()