import network
import socket
import time
from machine import I2C, Pin, ADC
from htu21d import HTU21D
import json


ssid = 'mywifi'
password = 'wifi_password'

# Donanım pinleri
button_pin = 15   # Fiziksel buton (sensör yenileme)
led_pin = 2       # LED pin
battery_pin = 26  # ADC0 (batarya gerilimi)

# Wi-Fi bağlantısı
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
print("Wi-Fi'ya bağlanılıyor...", end="")
wlan.connect(ssid, password)
while not wlan.isconnected():
    print(".", end="")
    time.sleep(1)
print(f"\nBağlandık! IP adresim: {wlan.ifconfig()[0]}")

# I2C ve sensör ayarı
i2c = I2C(scl=Pin(1), sda=Pin(0))
sensor = HTU21D(i2c)

# Buton ve LED ayarları
button = Pin(button_pin, Pin.IN, Pin.PULL_UP)
led = Pin(led_pin, Pin.OUT)
led.value(1)
led_state = False

battery_adc = ADC(Pin(battery_pin))

def read_battery_voltage():
    raw = battery_adc.read()
    voltage = raw * (3.3 / 4095) * 2
    return voltage

temperature_log = []
humidity_log = []
MAX_LOG = 20

PORT = 8080
addr = socket.getaddrinfo('0.0.0.0', PORT)[0][-1]
server = socket.socket()
server.bind(addr)
server.listen(1)
server.settimeout(10)

print(f"Web sunucusu http://{wlan.ifconfig()[0]}:{PORT} üzerinde çalışıyor")

def read_sensor():
    temperature = sensor.read_temperature()
    humidity = sensor.read_humidity()
    return temperature, humidity

def log_sensor_data(temp, hum):
    if len(temperature_log) >= MAX_LOG:
        temperature_log.pop(0)
        humidity_log.pop(0)
    temperature_log.append(temp)
    humidity_log.append(hum)

def toggle_led():
    global led_state
    led_state = not led_state
    led.value(0 if led_state else 1)
    print(f"LED durumu: {'Açık' if led_state else 'Kapalı'}")

while True:
    if button.value() == 0:
        temperature, humidity = read_sensor()
        log_sensor_data(temperature, humidity)

    try:
        client, client_addr = server.accept()
        print('Bağlantı:', client_addr)
        request = client.recv(1024).decode('utf-8')
        print("Gelen istek:\n", request)

        if "GET /refresh" in request:
            temperature, humidity = read_sensor()
            log_sensor_data(temperature, humidity)
        elif "GET /ledtoggle" in request:
            toggle_led()
            temperature, humidity = read_sensor()
            log_sensor_data(temperature, humidity)
        else:
            temperature, humidity = read_sensor()
            log_sensor_data(temperature, humidity)

        temp_json = json.dumps(temperature_log)
        hum_json = json.dumps(humidity_log)

        html_template = """HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <title>Sensor Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ background: #1e1e2f; color: #f0f0f5; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 20px; }}
    h1 {{ color: #ff89bb; }}
    #clock {{ color: #c0c0ff; margin: 0.5em 0; }}
    button {{ background: #ff5f87; border: none; padding: 10px 20px; margin: 10px; border-radius: 10px; color: white; font-size: 1em; cursor: pointer; }}
    canvas {{ background: #ffffff10; border-radius: 15px; margin-top: 30px; }}
  </style>
</head>
<body>
  <h1>Sensor Dashboard 🌡️</h1>
  <div id="clock">Saat yükleniyor...</div>

  <p><strong>Sıcaklık:</strong> {temperature:.2f} °C</p>
  <p><strong>Nem:</strong> {humidity:.2f} %</p>

  <form action="/refresh" method="get">
    <button type="submit">Yenile 🔄</button>
  </form>
  <form action="/ledtoggle" method="get">
    <button type="submit">{led_text}</button>
  </form>

  <canvas id="sensorChart" width="400" height="200"></canvas>

  <script>
    const tempData = {temp_json};
    const humData = {hum_json};
    const labels = tempData.map((_, i) => i + 1);

    const ctx = document.getElementById('sensorChart').getContext('2d');
    const sensorChart = new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [
                {{
                    label: 'Sıcaklık (°C)',
                    data: tempData,
                    yAxisID: 'y',
                    borderColor: '#ff6384',
                    backgroundColor: 'rgba(255,99,132,0.1)',
                    fill: true
                }},
                {{
                    label: 'Nem (%)',
                    data: humData,
                    yAxisID: 'y1',
                    borderColor: '#36a2eb',
                    backgroundColor: 'rgba(54,162,235,0.1)',
                    fill: true
                }}
            ]
        }},
        options: {{
            responsive: true,
            scales: {{
                y: {{
                    type: 'linear',
                    position: 'left',
                    title: {{
                      display: true,
                      text: 'Sıcaklık (°C)'
                    }}
                }},
                y1: {{
                    type: 'linear',
                    position: 'right',
                    title: {{
                      display: true,
                      text: 'Nem (%)'
                    }},
                    grid: {{
                        drawOnChartArea: false
                    }}
                }}
            }}
        }}
    }});

    function updateClock() {{
      const now = new Date();
      document.getElementById('clock').textContent = "Saat: " + now.toLocaleTimeString('tr-TR');
    }}
    setInterval(updateClock, 1000);
    updateClock();

    const autoRefresh = setTimeout(() => location.reload(), 3000);
    document.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => clearTimeout(autoRefresh)));
  </script>
</body>
</html>
"""

        response = html_template.format(
            temperature=temperature,
            humidity=humidity,
            led_text="Işığı Kapat" if led_state else "Işığı Aç",
            temp_json=temp_json,
            hum_json=hum_json
        )

        client.send(response.encode('utf-8'))
        client.close()

    except OSError as e:
        print("Bağlantı zaman aşımına uğradı veya hata oluştu:", e)

