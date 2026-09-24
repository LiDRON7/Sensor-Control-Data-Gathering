import time
import math
from wakeup import wakeup

# ==============================
# Distance calculation with latitude, longitude, and altitude
# ==============================
def distance_breakdown(latitude1, longitude1, altitude1, latitude2, longitude2, altitude2):
    
    # === HORIZONTAL LEG (Haversine formula) ===
    #RADIUS = 20902230  # Earth's radius in feet
    RADIUS = 6371000    # Earth's radius in meters
    
    latitude1_radius = math.radians(latitude1)
    latitude2_radius = math.radians(latitude2)
    longitude1_radius = math.radians(longitude1)
    longitude2_radius = math.radians(longitude2)
    
    latitude_distance = latitude2_radius - latitude1_radius
    longitude_distance = longitude2_radius - longitude1_radius
    
    # Chord length square
    chord_length = math.sin(latitude_distance/2)**2 + math.cos(latitude1_radius) * math.cos(latitude2_radius) * math.sin(longitude_distance/2)**2
    # Angular distance
    angular_distance = 2 * math.atan2(math.sqrt(chord_length), math.sqrt(1-chord_length))
    
    horizontal_distance = RADIUS * angular_distance
    
    # === VERTICAL LEG ===
    # Calculate altitude difference in meters
    vertical_distance = (altitude2 - altitude1)  
    
    # === DIAGONAL (3D straight-line distance) ===
    real_distance = math.sqrt(horizontal_distance**2 + vertical_distance**2)
    

    return real_distance

# Wake up Pixhawk and request streams
the_connection = wakeup()

try:
    while True:
        # Get attitude and coordinates
        attitude = the_connection.recv_match(type=['GLOBAL_POSITION_INT','ATTITUDE', 'GPS_RAW_INT'], blocking=False) # type = 'ATTITUDE'

        if not attitude: 
            continue

        # Show coordinates coordinates
        if attitude.get_type() == 'GLOBAL_POSITION_INT':
            gps_lat = attitude.lat / 1e7
            gps_lon = attitude.lon / 1e7
            gps_alt = attitude.alt / 1000.0
            #distance = distance_breakdown(gps_lat,gps_lon, gps_alt, home_base_lat,home_base_lon, home_base_alt) 

            print("---- GLOBAL POSITION ----")
            print(f"Latitude: {gps_lat}")
            print(f"Longitude: {gps_lon}")
            print(f"Altitude: {gps_alt} m \n")
            #print(f"Distance: {distance} m")  
        
        # Show attitude
        if attitude.get_type() == 'ATTITUDE':
            print("\n---- ATTITUDE ----")
            print(f"Attitude -> Roll: {attitude.roll:.2f}, Pitch: {attitude.pitch:.2f}, Yaw: {attitude.yaw:.2f}")
            print(f"Angular rates -> p: {attitude.rollspeed:.2f}, q: {attitude.pitchspeed:.2f}, r: {attitude.yawspeed:.2f}\n")
        
        if attitude.get_type() == 'GPS_RAW_INT':
            fix_type = attitude.fix_type
            satellites = attitude.satellites_visible  
            print(f"Fix Type: {fix_type}")
            print(f"Satellites: {satellites}")

        time.sleep(0.05)  # slow down printing a bit
except KeyboardInterrupt:
    print("Stopped by user")
