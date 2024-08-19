1. Copy service file into `systemd` folder
```Bash
sudo cp sensor.service /lib/systemd/system/sensor.service
```

2. Modfiy accessibility to service unit
```Bash
sudo chmod 644 /lib/systemd/system/sensor.service
```

3. Modify access to python script
```Bash
chmod +x /home/toor/birdbox_sensors/main.py
```

4. Reload daemon
```Bash
sudo systemctl daemon-reload
```

5. Activate service
```Bash
sudo systemctl enable sensor.service
```

6. Run service
```Bash
sudo systemctl start sensor.service
```