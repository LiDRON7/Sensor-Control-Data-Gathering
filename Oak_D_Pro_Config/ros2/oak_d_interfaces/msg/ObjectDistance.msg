# Object class name from the model, or its numeric label as a string.
# Multiple objects may have the same class; this is not a tracking ID.
string class_id

# Median depth in the central ROI, in meters along the RGB camera's optical Z
# axis. This is not Euclidean range or a 3D object pose.
# NaN when distance_valid is false.
float32 distance_m
bool distance_valid
