# Known issues on the drone's Pi

Problems we hit while setting up `lidron-cranberry` (Ubuntu 25.10, Raspberry Pi 5), on Oct 28, 2026. Each one has what you see, why it happens, the fix, and how to check it's still fixed.

The setup steps that prevent all of these are in [pi-setup.md](pi-setup.md). Read this page when something that used to work stops working.

## Check all of them at once

Run this on the Pi. Every line should say `OK`:

```bash
systemctl is-enabled serial-getty@ttyAMA0 2>/dev/null | grep -q masked && echo "OK login console off" || echo "FIX 1: login console on TELEM2"
grep -q "console=serial0" /boot/firmware/current/cmdline.txt && echo "FIX 1: kernel console on TELEM2" || echo "OK kernel console off"
id -nG | grep -qw docker && id -nG | grep -qw dialout && echo "OK groups" || echo "FIX 3: docker/dialout groups"
test -f /etc/udev/rules.d/80-movidius.rules && echo "OK camera udev rule" || echo "FIX 4: camera udev rule"
docker exec lidron_autonomy env | grep -q FASTDDS_BUILTIN_TRANSPORTS=UDPv4 && echo "OK dds over udp" || echo "FIX 2: dds shared memory"
```

## 1. Ubuntu uses the TELEM2 serial port as a login console

**What you see:** `px4-agent` never prints `create_client`, autonomy has no `/fmu` topics, and almost no bytes arrive on `/dev/ttyAMA0`. The wiring looks right.

**Why:** Ubuntu turns on two things on the GPIO UART by default:

- `serial-getty@ttyAMA0`, a login prompt that reads every byte PX4 sends, so `px4-agent` never gets them.
- `console=serial0,115200` on the kernel command line, which sends Linux boot messages to the Pixhawk.

**Fix:**

```bash
sudo systemctl mask --now serial-getty@ttyAMA0.service
sudo sed -i "s/console=serial0,115200 //" /boot/firmware/current/cmdline.txt
sudo reboot
```

**Check:** `systemctl is-enabled serial-getty@ttyAMA0` says `masked`, and `cat /boot/firmware/current/cmdline.txt` has no `serial0`.

**Can it come back?** Yes. A kernel update can rewrite `cmdline.txt`. If TELEM2 stops working after `apt upgrade`, check this first.

## 2. Autonomy can't see the sensor topics

**What you see:** `ros2 topic hz /oakd/depth/points` works inside `oak-d` but shows nothing inside `lidron_autonomy`.

**Why:** Fast DDS sends data between containers through shared memory in `/dev/shm`. The containers run as different users (`oak`, `airborne`, `root`), so they can't open each other's files, and it fails without an error.

**Fix:** every container uses UDP instead. `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` is set in `compose.yaml` here and in `integration/compose.hardware.yml` in Autonomous-Systems. Any new container needs it too.

**Check:** the last line of the check script above.

## 3. Docker or the serial ports say "permission denied"

**What you see:** `permission denied while trying to connect to the docker API`, or a container can't open `/dev/ttyACM0`.

**Fix:** `sudo usermod -aG docker,dialout $USER`, then log out and back in.

## 4. The camera container keeps restarting

**What you see:** `oak-d` logs `No available devices` and `Insufficient permissions to communicate with X_LINK_UNBOOTED device`.

**Why:** the OAK-D needs a udev rule so non-root users can open it.

**Fix:**

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then unplug and replug the camera.

**Also:** plug it into a blue USB 3 port. In a black USB 2 port it still works, but slower.

## 5. PX4 settings after flashing

**What you see:** PX4 1.15 is flashed, but `px4-agent` gets nothing.

**Why:** flashing resets `UXRCE_DDS_CFG` to `0` (DDS off).

**Fix:** set `UXRCE_DDS_CFG = 102`, `SER_TEL2_BAUD = 921600` and `MAV_1_CONFIG = 0` in QGroundControl, then reboot the Pixhawk.

**Also happened:** on Oct 29 we set `UXRCE_DDS_CFG` with a pymavlink script. It sent `102` as a float, so PX4 saved `1120665600`, but reading it back over MAVLink still showed `102`. PX4 didn't start the DDS client at boot, and `uxrce_dds_client status` said `not running`. Setting it with `param set UXRCE_DDS_CFG 102` in the MAVLink Console fixed it.

**Check:** in the MAVLink Console (QGroundControl → Analyze Tools), `param show UXRCE_DDS_CFG` prints exactly `102` and `uxrce_dds_client status` says `Running`.

## 6. The radio has a different name

**What you see:** `airborne-bridge` won't start and the error names a `/dev/serial/by-id/...FTDI...` path.

**Why:** every SiK radio has its own serial number in its name.

**Fix:** put the name from `ls /dev/serial/by-id/` in `RADIO_DEVICE` in `.env`.

## 7. The Pi went offline while rewiring

**What happened:** the Pi lost power while TELEM2 wires were moved on its pins with it on. A wire probably touched a 5V pin (pin 2 or 4).

**Do this instead:** turn the Pi off before you touch the GPIO pins, and keep TELEM2 wire 1 (5 V) taped off.

## 8. The Tailscale login link expired

**What you see:** SSH prints `Tailscale SSH requires an additional check` with a link, and the link says it expired.

**Why:** Tailscale SSH is in "check" mode, so it asks you to approve in the browser now and then. Each link only works for a few minutes.

**Fix:** run `ssh lidron-cranberry@lidron-cranberry` again to get a new link, and open it right away with the LiDRON account.

## 9. TELEM2 wired RX to RX

**What you see:** `px4-agent` has no `create_client`, and `timeout 4 cat /dev/ttyAMA0 | wc -c` prints `0`, even though `uxrce_dds_client status` on the Pixhawk says `Running`.

**Why:** the Pixhawk's RX wire was on the Pi's RX pin. Each side has to send on its TX into the other side's RX.

**Fix:** turn the Pi off, then wire white (Pixhawk TX) to Pi pin 10 (RXD), yellow (Pixhawk RX) to Pi pin 8 (TXD), and black (GND) to Pi pin 6. See the drawing in [pi-setup.md](pi-setup.md#1-connect-the-hardware).

## 10. The camera keeps disconnecting

**What you see:** `oak-d` keeps restarting with `No available devices`, even though the udev rule from issue 4 is there, and `/oakd/depth/points` is never published. Seen on Nov 2 and Nov 5, 2026.

**Why:** the camera shows up as `03e7:2485` (Movidius MyriadX), loads its firmware, comes back as `03e7:f63b` (Luxonis Device), then drops within a few seconds and starts over. It drops when it starts drawing more current, so the most likely cause is not enough power: the Pi 5 limits USB to 600 mA when it doesn't detect a 5 A supply, and our step-down can't tell it that. On Nov 2 it also logged `over-current` on every USB port, and the Pi logged `Undervoltage detected!` at boot on Nov 5. A bad cable or a USB 2 port can look the same, so rule those out first.

**Check it live:** run these on the Pi (see [connect-to-pi.md](connect-to-pi.md)). Press `Ctrl+C` to stop the ones that keep running.

```bash
# 1. Watch the camera connect and drop. Bad: 2485, f63b, USB disconnect, over and over. Good: one f63b line, then nothing.
journalctl -kf | grep --line-buffered -E "03e7|USB disconnect"

# 2. Is it connected right now? Good: it stays on 03e7:f63b Luxonis Device.
watch -n1 'lsusb | grep 03e7'

# 3. Why the container fails. Good: it keeps running with no traceback.
docker logs -f --tail 20 oak-d

# 4. Does autonomy get depth? Good: about 13 Hz. Bad: "does not appear to be published yet".
auto() { docker exec lidron_autonomy bash -c "source /opt/ros/jazzy/setup.bash && source /autonomy/install/setup.bash && $*"; }
auto ros2 topic hz /oakd/depth/points

# 5. Is power dropping? Any line here while the camera loops points to power.
journalctl -kf | grep --line-buffered -iE "voltage|over-current"
```

**Fix, in order:**

1. Plug the camera into a blue USB 3 port.
2. Plug it into a laptop with the same cable. If it runs steadily there, the camera and cable are fine and the Pi isn't giving it enough power.
3. Give the camera more power: a USB Y-cable or powered hub with its own 5 V feed, or a 5 V/5 A step-down plus `usb_max_current_enable=1` in `/boot/firmware/config.txt`. Don't turn that setting on with a 3 A step-down. It only removes the limit, it doesn't add power.

**Check:** check 1 stays quiet after one `f63b` line, and check 4 shows about 13 Hz.
