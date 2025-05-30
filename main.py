import network
import socket
import time
import ure
from machine import ADC, Pin
#Capturamos los valores del modulo
mq2 = ADC(Pin(32))
mq2.atten(ADC.ATTN_11DB)

# Configuración del punto de acceso
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid='ESP32-AP', password='12345678', authmode=network.AUTH_WPA_WPA2_PSK)

# Esperar a que el AP se active
while not ap.active():
    time.sleep(1)
print('Access Point activo con IP:', ap.ifconfig()[0])

# Conjunto para rastrear clientes conectados
known_clients = set()

# Función para detectar nuevos clientes
def check_new_clients():
    global known_clients
    try:
        stations = ap.status('stations')
        current = set()
        for s in stations:
            if isinstance(s, tuple) and len(s) == 2:
                mac, _ = s
                current.add(bytes(mac))
        newbies = current - known_clients
        for mac in newbies:
            mac_str = ':'.join('{:02x}'.format(b) for b in mac)
            print('Nuevo cliente conectado:', mac_str)
        known_clients = current
    except Exception as e:
        print('Error al verificar clientes conectados:', e)
# Esta funcion la creé con el proposito de replicar la función de una vascula, el te "tara", para establecer el valor de inicio para posteriormente
# Leer los proximos 500 valores del sensor, esto se reiniciará en cada reinicio
def gas_porcentaje(sensor_val, tara=0, ref=500):
    porcentaje = ((sensor_val - tara) / ref) * 100
    if porcentaje < 0:
        porcentaje = 0
    elif porcentaje > 100:
        porcentaje = 100
    return round(porcentaje, 2)

# Cargamos contenido de index.html del sistema de archivos
try:
    with open('index.html', 'r') as f:
        html = f.read()
except OSError:
    html = '<html><body><h1>Archivo no encontrado</h1></body></html>'

# Creammos un socket HTTP
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
sock = socket.socket()
sock.bind(addr)
sock.listen(1)
print('Servidor HTTP escuchando en', addr)
# Esto es para "tarar" los valores y definir el nuevo estado base
tara = 0
while True:
    # Verificamos nuevas conexiones al AP
    check_new_clients()

    # Aceptará la petición HTTP
    cl, client_addr = sock.accept()
    print('Petición de', client_addr)
    req = cl.recv(1024)
    try:
        req_str = req.decode('utf-8')
    except:
        cl.close()
        continue

    # Parseamos la ruta del GET
    path = '/'
    match = ure.search(r"GET\s+(/[^\s]*)", req_str)
    if match:
        path = match.group(1)
    print('Ruta solicitada:', path)

    # Responderá según la ruta
    if path == '/status':
        response = 'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK'
        cl.send(response)
    elif path == '/' or path == '/index.html':
        cl.send('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
        cl.send(html)
    elif path == '/api/sensor-data':
        gas_val = gas_porcentaje(mq2.read(), tara,500)
        print(f"Lectura de gas_val es {gas_val}")
        json = '{{"gasLevel": {}, "smokeLevel": {}}}'.format(gas_val, gas_val)
        cl.send('HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n')
        cl.send(json)
    elif path == '/api/tara':
        # Esto es para establecer el nuevo valor "base"
        tara = mq2.read()
        print("Se ha establecido una nueva base, se empezará a leer desde: ", tara)
    else:
        cl.send('HTTP/1.0 404 Not Found\r\nContent-Type: text/plain\r\n\r\n404')

    cl.close()
