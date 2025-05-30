# esp32_ap_server.py (ampliado)

import network
import socket
import ure as re
import ujson
import time

# --- 1. Configurar el ESP32 como Access Point ---
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid='GasMonitor_AP', authmode=network.AUTH_WPA_WPA2_PSK, password='12345678')
print('AP activo, IP AP:', ap.ifconfig()[0])

# --- 2. Preparar interfaz STA (para luego conectar a Wi-Fi real) ---
sta = network.WLAN(network.STA_IF)
sta.active(True)

# --- 3. Crear servidor HTTP en el puerto 80 ---
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)
print('Servidor HTTP escuchando en', addr)

def parse_request(conn):
    request = b''
    while b'\r\n\r\n' not in request:
        request += conn.recv(512)
    header, _, rest = request.partition(b'\r\n\r\n')
    lines = header.split(b'\r\n')
    method, path, _ = lines[0].split(b' ', 2)
    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith(b'content-length:'):
            content_length = int(line.split(b':')[1].strip())
    body = rest
    while len(body) < content_length:
        body += conn.recv(512)
    return method.decode(), path.decode(), body

def handle_wifi_connect(data):
    try:
        creds = ujson.loads(data)
        ssid = creds.get('ssid')
        pwd  = creds.get('password')
        if not ssid or not pwd:
            raise ValueError
        sta.connect(ssid, pwd)
        for _ in range(15):
            if sta.isconnected():
                break
            time.sleep(1)
        if sta.isconnected():
            return 200, {'status':'ok','ip':sta.ifconfig()[0]}
        else:
            return 500, {'status':'error','message':'No pudo conectar'}
    except:
        return 400, {'status':'error','message':'Datos inválidos'}

def handle_wifi_scan():
    # devuelve lista de redes: [(ssid, bssid, channel, RSSI, authmode, hidden), ...]
    nets = sta.scan()
    lista = []
    for ssid_raw, bssid, chan, rssi, auth, hidden in nets:
        ssid = ssid_raw.decode('utf-8')
        # Si el SSID está vacío o solo espacios, no lo agregamos
        if not ssid.strip():
            continue

        lista.append({
            'ssid': ssid,
            'bssid': ':'.join('{:02x}'.format(b) for b in bssid),
            'channel': chan,
            'rssi': rssi,
            'authmode': auth,
            'hidden': bool(hidden)
        })
    return 200, {'status':'ok', 'networks': lista}

def handle_wifi_status():
    if sta.isconnected():
        return 200, {'status':'connected','ip':sta.ifconfig()[0]}
    else:
        return 200, {'status':'disconnected'}

while True:
    conn, addr = s.accept()
    print('Cliente desde', addr)
    try:
        method, path, body = parse_request(conn)
        print('>>', method, path)
        if method == 'POST' and path == '/wifi/connect':
            status, response = handle_wifi_connect(body)
        elif method == 'GET' and path == '/wifi/status':
            status, response = handle_wifi_status()
        elif method == 'GET' and path == '/wifi/scan':
            status, response = handle_wifi_scan()
            print(f'El estatus es {status} y la respuesta es {resp}')
        else:
            status, response = 404, {'status':'error','message':'No encontrado'}
        resp = ujson.dumps(response)
        print('la función retorna', response,' pero resp es', resp)
        conn.send('HTTP/1.1 {} OK\r\n'.format(status))
        conn.send('Content-Type: application/json\r\n')
        conn.send('Content-Length: {}\r\n'.format(len(resp)))
        conn.send('\r\n')
        print('En conn.send resp enviando:', resp)
        conn.send(resp)
    except Exception as e:
        print('Error:', e)
    finally:
        conn.close()
