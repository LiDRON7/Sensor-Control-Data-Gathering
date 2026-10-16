# ROS 2 component voltage monitoring

`vlp16_voltage_monitor` publishes live supply voltage, readable status, and
warnings while robot components operate. It includes a native Ethernet reader
for the Velodyne VLP-16 and a configurable ROS topic adapter for USB telemetry
radios, the USB OAK-D Pro, and other cameras or sensors with available voltage
measurements. The existing package name and Velodyne text topic are preserved.

## Supported measurement sources

| Component | Voltage source | Setup needed |
| --- | --- | --- |
| Velodyne VLP-16 | HTTP `/cgi/diag.json`, field `volt_temp.bot.pwr_v_in` | Reachable sensor IPv4 address |
| USB telemetry radio | Existing driver or external power monitor topic | Identify the radio supply measurement and configure its topic |
| USB OAK-D Pro | Existing voltage-capable driver or external power monitor topic | Identify the camera supply measurement and configure its topic |
| Other camera or sensor | Any supported voltage topic | Run another adapter with a unique device name |

USB connectivity by itself does not provide a measured supply voltage. The USB
adapters do not open serial ports, take ownership of the camera, or generate
assumed 5 V readings. They need a real measurement publisher running alongside
the component. If no voltage interface is available, an external measurement
device and its ROS driver are needed. The supplied launch disables the radio
and camera adapters until you enable them; their input topics are intentionally
blank so enabling an unconfigured adapter reports a configuration error.

The documented DepthAI `SystemInformation` fields cover temperatures and
resource usage, without a supply-voltage field. Do not interpret those values as
voltage. For MAVLink radios, `RADIO_STATUS` carries link statistics, without a
supply-voltage field. A vehicle battery topic also does not necessarily measure
the radio or camera supply. Confirm the physical rail represented by each input.
See [DepthAI SystemInformation](https://docs.luxonis.com/software/depthai-components/messages/system_information)
and [MAVLink RADIO_STATUS](https://mavlink.io/en/messages/common.html#RADIO_STATUS).

The Velodyne conversion is `volts = raw * 5.0 / 4096.0 * 11.0`, following the
[VLP-16 manual](https://data.ouster.io/downloads/velodyne/user-manual/vlp-16-user-manual-revf.pdf).
Its initial 8–19 V warning limits follow the input-power diagnostic range in
the [Rev E manual, section 10.2.3.3.15](https://docs.clearpathrobotics.com/assets/files/clearpath_robotics_011703-TDS1-e0837d8436bb21caf9d84acc8237d4ea.pdf).
Choose narrower operating limits if your installation requires them.

## Build and run the Velodyne monitor

From the ROS workspace root:

```bash
cd /home/jankii/Documents/Voltage_Meter_ROS2/velodyne_voltage
source /opt/ros/jazzy/setup.bash
colcon build --packages-select vlp16_voltage_monitor
source install/setup.bash
ros2 launch vlp16_voltage_monitor voltage_monitor.launch.py sensor_ip:=192.168.1.201
```

Use the sensor's address for `sensor_ip`, not the computer's address. The
computer's Ethernet interface must have a distinct address on the same subnet.
You can check the endpoint with
`curl --noproxy '*' --max-time 2 http://192.168.1.201/cgi/diag.json`.
This package does not change IPv4 settings, motor speed, or camera/radio operation.

For example, enable a warning for a change greater than 1 V between samples:

```bash
ros2 launch vlp16_voltage_monitor voltage_monitor.launch.py \
  sensor_ip:=192.168.1.201 max_step_voltage:=1.0
```

## Run several components

Edit `config/voltage_monitors.yaml` in the source package (or copy it to your
own configuration path). Set the USB adapters' `input_topic`, `input_type`, and
warning thresholds from the actual devices and power rails. Numeric ROS
parameters use floating-point YAML values, for example `5.0` rather than `5`.

Inspect existing sources while their drivers are running:

```bash
ros2 topic list -t
ros2 topic info /your/voltage_topic --verbose
ros2 topic echo /your/voltage_topic --once
```

After configuring real sources, launch all three monitors:

```bash
ros2 launch vlp16_voltage_monitor voltage_monitors.launch.py \
  config_file:=/absolute/path/to/voltage_monitors.yaml \
  enable_telemetry:=true enable_oakd:=true
```

`enable_velodyne` defaults to `true`; `enable_telemetry` and `enable_oakd` default
to `false`. Each monitor runs in a separate process, so a Velodyne HTTP timeout
does not block the radio or camera adapters. Start the source drivers separately.
The YAML node keys must match the launch node names:
`vlp16_voltage_monitor`, `telemetry_voltage_monitor`, and `oakd_voltage_monitor`.

For an additional sensor, run another adapter. This example uses an illustrative
5 V rail and topic; choose limits appropriate to the actual device:

```bash
ros2 run vlp16_voltage_monitor voltage_topic_monitor --ros-args \
  -r __node:=front_camera_voltage_monitor \
  -p device_name:=front_camera \
  -p input_topic:=/power/front_camera_voltage \
  -p input_type:=std_msgs/msg/Float32 \
  -p min_voltage:=4.75 -p max_voltage:=5.25 -p max_step_voltage:=0.25
```

## Published topics

For each enabled device (`velodyne`, `telemetry`, `oakd`, or your `device_name`):

| Topic | ROS 2 type | Content |
| --- | --- | --- |
| `/<device>/voltage` | `std_msgs/msg/String` | `Voltage: 12.22 V` or `Voltage: unavailable` |
| `/<device>/voltage_value` | `std_msgs/msg/Float64` | Fresh valid numeric measurements in volts, suitable for plotting |
| `/<device>/voltage_status` | `std_msgs/msg/String` | `OK: ...` or `WARNING: ...` with the reason |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | Timestamped component status, voltage, sample age, and configured limits |

Device topics are relative to the node namespace; `/diagnostics` is shared and
absolute. Each array contains one monitor's status, named `voltage/<device>`
(or `voltage/<namespace>/<device>`). Combine statuses by name when displaying
multiple components. Use distinct device names or namespaces for multiple radios
or cameras. Outputs are reliable, volatile, depth 10. Topic inputs are best effort,
volatile, depth 5, allowing connection to either reliable or best-effort publishers.

In another terminal, source ROS and the workspace before running:

```bash
ros2 topic echo /velodyne/voltage --field data
ros2 topic echo /velodyne/voltage_status --field data
ros2 topic echo /diagnostics
```

Use `/velodyne/voltage_value/data` in `rqt_plot` if it is installed. Numeric
messages have no timestamp; use diagnostics for sample age and status. No numeric
sample is published on failure or staleness. A plot may still display its last
point, so consumers must also check status or their own receipt timeout.

## Warning behavior and timing

- Low/high warnings occur strictly below/above the configured limits. Values
  exactly at a limit are accepted. Zero disables that individual threshold.
- Sudden-change warnings compare adjacent fresh valid samples using absolute
  voltage difference, not a rate per second. The warning lasts until the next
  sample changes the assessment. A source failure or stale gap resets this
  comparison baseline. This detects sample-to-sample steps, not all electrical
  ripple or transients between samples.
- Missing, invalid, NaN, infinite, negative, or disconnected readings produce
  unavailable status. Zero volts is a valid reading and can trigger a low warning.
- Diagnostics use `OK` (0), `WARN` (1) for voltage irregularities, and `STALE` (3)
  for unavailable measurements. Range warnings do not suppress valid numeric data.
- Status is published on each reading and every 0.5 seconds. Warning logs appear
  when the condition changes, then at most once per `warning_repeat_sec` for the
  same condition. A recovery message is logged when the status returns to OK.
- Velodyne defaults to 1 Hz, with polling never configured faster than 1 Hz in
  accordance with its HTTP guidance. Topic adapters process measurements as they
  arrive. These are live monitoring nodes, not hard real-time acquisition systems.
- Freshness uses local monotonic receipt time, independent of `/clock`; upstream
  publishers must provide new measurements rather than repeatedly replay old ones.
  With no incoming messages, stale status is detected on the next 0.5 s watchdog
  tick. Velodyne's synchronous HTTP read can delay its own callbacks by its socket
  timeout; the timeout is not a total deadline for a server that trickles bytes.

## Configuration parameters

Parameters are read-only after startup. Change the YAML/launch arguments and
restart the affected monitor. YAML settings for the multi-device launch come
from `config_file`; the single-Velodyne launch exposes timing, logging, and warning
settings directly as launch arguments. Other settings can be passed with
`ros2 run ... --ros-args -p name:=value`.

| Shared parameter | Default | Meaning |
| --- | --- | --- |
| `device_name` | `velodyne` / `sensor` | Output topic prefix; one ROS name token. YAML uses `telemetry` and `oakd` for USB adapters |
| `min_voltage` | `8.0` Velodyne, `0.0` adapter | Low warning threshold in volts; zero disables |
| `max_voltage` | `19.0` Velodyne, `0.0` adapter | High warning threshold in volts; zero disables |
| `max_step_voltage` | `0.0` | Consecutive-sample change threshold in volts; zero disables |
| `stale_timeout_sec` | `3.0` | Positive maximum time without a valid sample |
| `warning_repeat_sec` | `10.0` | Positive interval for repeating an unchanged warning log |
| `log_readings` | `true` | Print each valid reading in the terminal; disable for high-rate inputs |

Radio/camera range and step checks are disabled until their thresholds are set;
freshness and invalid-data detection remain active. An OK status with disabled
limits means available valid data, not approval of the device's operating voltage.

| Velodyne parameter | Default | Meaning |
| --- | --- | --- |
| `sensor_ip` | `192.168.1.201` | Sensor IPv4 address |
| `poll_period_sec` | `1.0` | Finite polling interval, at least 1 second |
| `timeout_sec` | `0.8` | Positive HTTP socket timeout, no greater than polling interval |

For Velodyne, `stale_timeout_sec` must exceed `poll_period_sec + timeout_sec`.

| Topic adapter parameter | Default | Meaning |
| --- | --- | --- |
| `input_topic` | empty, required | Actual source topic; must not match a device output topic |
| `input_type` | `std_msgs/msg/Float32` | One of the types below |
| `voltage_scale` | `1.0` | Positive multiplier converting input units to volts; use `0.001` for millivolts |
| `diagnostic_name` | empty | Exact upstream status name, required for diagnostic input |
| `diagnostic_key` | empty | Exact upstream numeric voltage key, required for diagnostic input |

| Supported input type | Value used |
| --- | --- |
| `std_msgs/msg/Float32` | `data` |
| `std_msgs/msg/Float64` | `data` |
| `sensor_msgs/msg/BatteryState` | `voltage`; `present` must be true |
| `diagnostic_msgs/msg/DiagnosticArray` | Exact selected status/key; value must be a numeric string without a unit suffix |

Unrelated diagnostic statuses are ignored without refreshing freshness. A
matching status with a missing/ambiguous key, or ERROR/STALE level, marks the
measurement unavailable. WARN source status may still carry a usable measurement;
this monitor independently evaluates voltage and does not forward unrelated
driver warnings. Monitor-generated status names starting with `voltage/` are
rejected as inputs to prevent feedback on `/diagnostics`.

## Test without connected hardware

Run an adapter with explicitly simulated input and illustrative thresholds:

```bash
ros2 run vlp16_voltage_monitor voltage_topic_monitor --ros-args \
  -p device_name:=test_usb -p input_topic:=/test/usb_voltage \
  -p min_voltage:=4.75 -p max_voltage:=5.25 -p max_step_voltage:=0.25
```

In another sourced terminal, publish a normal reading:

```bash
ros2 topic pub --rate 2 /test/usb_voltage std_msgs/msg/Float32 '{data: 5.0}'
```

Stop that publisher and repeat with `{data: 4.5}` or `{data: 5.6}` to observe
low/high warnings. Stop publishing for more than three seconds to observe stale
status and `Voltage: unavailable`. Resume publishing 5.0 to observe recovery.
Inspect `/test_usb/voltage_status` and `/diagnostics` throughout the test.

Run automated tests from the package directory after sourcing ROS:

```bash
python3 -m pytest test -q
```

Hardware acceptance still requires comparing each reported voltage with an
independent measurement while its component operates and checking actual
disconnect/reconnect behavior. USB adapters cannot be hardware-validated until
their measurement source and device limits are identified.
