/**
 * PiDog Cloud Control - Interface JavaScript
 * Gère la communication avec le serveur et l'interface utilisateur
 */

// Configuration
const CONFIG = {
    refreshInterval: 1000,
    videoRefreshInterval: 200,
    detectionRefreshInterval: 500,
    clientStatusRefreshInterval: 5000,
    distanceChartMaxPoints: 20,
    videoPlaceholder: '/static/placeholder.jpg',
    explosionThreshold: 20 // cm
};

// Variables globales
let selectedClientId = null;
let autoMode = false;
let distanceHistory = [];
let distanceChart = null;
let lastVideoRefresh = 0;
let lastDetectionRefresh = 0;
let lastClientStatusRefresh = 0;
let clientCheckInterval = null;

// Éléments DOM
const elements = {
    connectionStatus: document.getElementById('connection-status'),
    noClientsMessage: document.getElementById('no-clients-message'),
    clientContainer: document.getElementById('client-container'),
    clientSelect: document.getElementById('client-select'),
    videoFeed: document.getElementById('video-feed'),
    detectionOverlay: document.getElementById('detection-overlay'),
    noCameraMessage: document.getElementById('no-camera-message'),
    distanceValue: document.getElementById('distance-value'),
    explosionWarning: document.getElementById('explosion-warning'),
    manualModeBtn: document.getElementById('manual-mode-btn'),
    autoModeBtn: document.getElementById('auto-mode-btn'),
    activityLog: document.getElementById('activity-log'),
    personsCount: document.getElementById('persons-count'),
    detectionConfidence: document.getElementById('detection-confidence'),
    inferenceTime: document.getElementById('inference-time'),
    cameraStatus: document.getElementById('camera-status'),
    imuStatus: document.getElementById('imu-status'),
    rgbStatus: document.getElementById('rgb-status'),
    distanceSensorStatus: document.getElementById('distance-sensor-status'),
    ipAddress: document.getElementById('ip-address'),
    clientConnectionTime: document.getElementById('client-connection-time'),
    distanceChart: document.getElementById('distance-chart'),
    lightMode: document.getElementById('light-mode'),
    lightColor: document.getElementById('light-color')
};

// Initialiser l'interface
function initializeUI() {
    // Initialiser le graphique de distance
    initializeDistanceChart();
    
    // Ajouter les écouteurs d'événements
    elements.clientSelect.addEventListener('change', handleClientChange);
    elements.manualModeBtn.addEventListener('click', () => setMode('manual'));
    elements.autoModeBtn.addEventListener('click', () => setMode('auto'));
    
    // Configurer les boutons de contrôle
    setupControlButtons();
    
    // Bouton des LED
    document.getElementById('btn-set-light').addEventListener('click', setRgbLight);
    
    // Démarrer la vérification périodique des clients
    startClientCheck();
    
    // Ajouter un message au journal
    addLogEntry('Interface initialisée', 'info');
}

// Initialiser le graphique de distance
function initializeDistanceChart() {
    const ctx = elements.distanceChart.getContext('2d');
    
    distanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Distance (cm)',
                data: [],
                borderColor: '#ff5f52',
                backgroundColor: 'rgba(255, 95, 82, 0.2)',
                borderWidth: 2,
                tension: 0.2,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    display: false
                },
                y: {
                    beginAtZero: true,
                    suggestedMax: 200,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
}

// Configurer les boutons de contrôle
function setupControlButtons() {
    // Boutons de mouvement et d'action
    const controlButtons = document.querySelectorAll('.control-btn[data-action]');
    controlButtons.forEach(button => {
        button.addEventListener('click', () => {
            const action = button.getAttribute('data-action');
            sendCommand(action);
        });
    });
}

// Gestionnaire de changement de client
function handleClientChange() {
    const newClientId = elements.clientSelect.value;
    if (newClientId !== selectedClientId) {
        selectedClientId = newClientId;
        addLogEntry(`Client sélectionné : ${selectedClientId}`, 'info');
        
        // Réinitialiser l'historique des distances
        distanceHistory = [];
        updateDistanceChart();
        
        // Mettre à jour immédiatement les informations du client
        fetchClientStatus();
        
        // Actualiser l'interface
        updateInterface();
    }
}

// Mettre à jour l'interface en fonction du client sélectionné
function updateInterface() {
    if (selectedClientId) {
        // Afficher le conteneur du client
        elements.noClientsMessage.style.display = 'none';
        elements.clientContainer.style.display = 'block';
        
        // Mettre à jour le flux vidéo et les détections
        updateVideoFeed();
        updateDetections();
    } else {
        // Aucun client sélectionné
        elements.noClientsMessage.style.display = 'block';
        elements.clientContainer.style.display = 'none';
    }
}

// Mettre à jour le flux vidéo
function updateVideoFeed() {
    if (!selectedClientId) return;
    
    const now = Date.now();
    if (now - lastVideoRefresh < CONFIG.videoRefreshInterval) return;
    
    lastVideoRefresh = now;
    
    // Ajouter un timestamp pour éviter la mise en cache
    const videoUrl = `/client/${selectedClientId}/latest_frame?t=${now}`;
    
    // Vérifier si l'élément existe avant de mettre à jour
    if (elements.videoFeed) {
        elements.videoFeed.src = videoUrl;
        
        // Gérer les erreurs de chargement d'image
        elements.videoFeed.onerror = () => {
            elements.noCameraMessage.style.display = 'flex';
            elements.videoFeed.src = CONFIG.videoPlaceholder;
        };
        
        elements.videoFeed.onload = () => {
            elements.noCameraMessage.style.display = 'none';
        };
    }
}

// Mettre à jour les détections
function updateDetections() {
    if (!selectedClientId) return;
    
    const now = Date.now();
    if (now - lastDetectionRefresh < CONFIG.detectionRefreshInterval) return;
    
    lastDetectionRefresh = now;
    
    fetch(`/client/${selectedClientId}/latest_detection?t=${now}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Aucune détection disponible');
            }
            return response.json();
        })
        .then(data => {
            // Mettre à jour les statistiques de détection
            updateDetectionStats(data);
            
            // Dessiner les boîtes de détection
            drawDetectionBoxes(data.detections);
        })
        .catch(error => {
            console.error('Erreur lors de la récupération des détections:', error);
        });
}

// Mettre à jour les statistiques de détection
function updateDetectionStats(data) {
    if (!data) return;
    
    // Nombre de personnes détectées
    const personsCount = data.detections ? data.detections.length : 0;
    elements.personsCount.textContent = personsCount;
    
    // Confiance maximale
    let maxConfidence = 0;
    if (data.detections && data.detections.length > 0) {
        maxConfidence = Math.max(...data.detections.map(d => d.confidence));
        elements.detectionConfidence.textContent = maxConfidence.toFixed(2);
    } else {
        elements.detectionConfidence.textContent = '0.00';
    }
    
    // Temps d'inférence
    if (data.inference_time) {
        elements.inferenceTime.textContent = `${(data.inference_time * 1000).toFixed(1)} ms`;
    } else {
        elements.inferenceTime.textContent = '--';
    }
}

// Dessiner les boîtes de détection
function drawDetectionBoxes(detections) {
    // Effacer les détections précédentes
    const overlay = elements.detectionOverlay;
    overlay.innerHTML = '';
    
    if (!detections || detections.length === 0) return;
    
    // Créer un canvas SVG pour les détections
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    
    // Dessiner chaque détection
    detections.forEach(detection => {
        const { x1, y1, x2, y2, width, height } = detection.bbox;
        const confidence = detection.confidence;
        
        // Calculer les coordonnées relatives (pourcentage)
        const videoWidth = elements.videoFeed.naturalWidth || 640;
        const videoHeight = elements.videoFeed.naturalHeight || 480;
        
        const relX = (x1 / videoWidth) * 100;
        const relY = (y1 / videoHeight) * 100;
        const relWidth = (width / videoWidth) * 100;
        const relHeight = (height / videoHeight) * 100;
        
        // Créer le rectangle
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', `${relX}%`);
        rect.setAttribute('y', `${relY}%`);
        rect.setAttribute('width', `${relWidth}%`);
        rect.setAttribute('height', `${relHeight}%`);
        rect.setAttribute('fill', 'none');
        rect.setAttribute('stroke', `rgba(255, 0, 0, ${confidence})`);
        rect.setAttribute('stroke-width', '2');
        
        // Créer l'étiquette
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', `${relX}%`);
        text.setAttribute('y', `${relY - 0.5}%`);
        text.setAttribute('fill', '#ff5f52');
        text.setAttribute('font-size', '12px');
        text.textContent = `Personne: ${(confidence * 100).toFixed(0)}%`;
        
        // Ajouter au SVG
        svg.appendChild(rect);
        svg.appendChild(text);
    });
    
    // Ajouter le SVG à l'overlay
    overlay.appendChild(svg);
}

// Vérifier périodiquement les clients disponibles
function startClientCheck() {
    // Vérifier immédiatement
    checkAvailableClients();
    
    // Configurer la vérification périodique
    clientCheckInterval = setInterval(checkAvailableClients, CONFIG.refreshInterval);
    
    // Configurer la mise à jour périodique de l'interface
    setInterval(updateInterface, CONFIG.refreshInterval);
}

// Vérifier les clients disponibles
function checkAvailableClients() {
    fetch('/clients')
        .then(response => response.json())
        .then(data => {
            updateClientsList(data.clients, data.status);
            updateConnectionStatus(data.clients.length > 0);
        })
        .catch(error => {
            console.error('Erreur lors de la vérification des clients:', error);
            updateConnectionStatus(false);
        });
}

// Mettre à jour la liste des clients
function updateClientsList(clients, status) {
    // Sauvegarder la sélection actuelle
    const currentSelection = elements.clientSelect.value;
    
    // Effacer la liste actuelle
    elements.clientSelect.innerHTML = '';
    
    if (clients.length === 0) {
        // Aucun client disponible
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '-- Aucun robot connecté --';
        elements.clientSelect.appendChild(option);
        elements.clientSelect.disabled = true;
        
        // Réinitialiser la sélection
        selectedClientId = null;
    } else {
        // Ajouter les clients disponibles
        elements.clientSelect.disabled = false;
        
        clients.forEach(clientId => {
            const option = document.createElement('option');
            option.value = clientId;
            option.textContent = clientId;
            elements.clientSelect.appendChild(option);
        });
        
        // Restaurer la sélection précédente si possible
        if (currentSelection && clients.includes(currentSelection)) {
            elements.clientSelect.value = currentSelection;
        } else {
            // Sinon, sélectionner le premier client
            elements.clientSelect.value = clients[0];
            selectedClientId = clients[0];
        }
    }
    
    // Mettre à jour l'interface
    updateInterface();
}

// Mettre à jour le statut de connexion
function updateConnectionStatus(connected) {
    const statusDot = elements.connectionStatus.querySelector('.status-dot');
    const statusText = elements.connectionStatus.querySelector('.status-text');
    
    if (connected) {
        statusDot.className = 'status-dot online';
        statusText.textContent = 'Connecté';
        elements.connectionStatus.title = 'Connexion au serveur établie';
    } else {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'Déconnecté';
        elements.connectionStatus.title = 'Connexion au serveur perdue';
    }
}

// Mettre à jour le statut du client
function fetchClientStatus() {
    if (!selectedClientId) return;
    
    const now = Date.now();
    if (now - lastClientStatusRefresh < CONFIG.clientStatusRefreshInterval) return;
    
    lastClientStatusRefresh = now;
    
    fetch(`/client/${selectedClientId}/status?t=${now}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Impossible de récupérer le statut du client');
            }
            return response.json();
        })
        .then(status => {
            updateClientStatus(status);
        })
        .catch(error => {
            console.error('Erreur lors de la récupération du statut du client:', error);
        });
}

// Mettre à jour le statut du client dans l'interface
function updateClientStatus(status) {
    if (!status) return;
    
    // Statut de la caméra
    elements.cameraStatus.textContent = status.has_camera ? 'Disponible' : 'Non disponible';
    elements.cameraStatus.className = 'status-value ' + (status.has_camera ? 'log-success' : 'log-error');
    
    // Statut de l'IMU
    elements.imuStatus.textContent = status.has_imu ? 'Disponible' : 'Non disponible';
    elements.imuStatus.className = 'status-value ' + (status.has_imu ? 'log-success' : 'log-error');
    
    // Statut des LEDs RGB
    elements.rgbStatus.textContent = status.has_rgb ? 'Disponible' : 'Non disponible';
    elements.rgbStatus.className = 'status-value ' + (status.has_rgb ? 'log-success' : 'log-error');
    
    // Statut du capteur de distance
    elements.distanceSensorStatus.textContent = status.has_distance_sensor ? 'Disponible' : 'Non disponible';
    elements.distanceSensorStatus.className = 'status-value ' + (status.has_distance_sensor ? 'log-success' : 'log-error');
    
    // Adresse IP
    if (status.ip_address) {
        elements.ipAddress.textContent = status.ip_address;
    }
    
    // Durée de connexion
    if (status.last_update) {
        const connectedDuration = Math.floor((Date.now() / 1000) - status.last_update);
        elements.clientConnectionTime.textContent = formatDuration(connectedDuration);
    }
    
    // Vérifier les données du capteur de distance
    if (status.sensors && status.sensors.distance) {
        const distance = status.sensors.distance.value;
        updateDistance(distance);
    }
    
    // Afficher/masquer la caméra en fonction de la disponibilité
    if (!status.has_camera) {
        elements.noCameraMessage.style.display = 'flex';
    }
}

// Mettre à jour la distance affichée
function updateDistance(distance) {
    if (distance === null || distance === undefined) return;
    
    // Mettre à jour la valeur affichée
    elements.distanceValue.textContent = distance.toFixed(1);
    
    // Mettre à jour l'historique et le graphique
    addDistanceToHistory(distance);
    
    // Vérifier le seuil d'explosion
    if (distance < CONFIG.explosionThreshold) {
        elements.explosionWarning.style.display = 'flex';
    } else {
        elements.explosionWarning.style.display = 'none';
    }
}

// Ajouter une distance à l'historique
function addDistanceToHistory(distance) {
    const timestamp = new Date().toLocaleTimeString();
    
    distanceHistory.push({
        time: timestamp,
        value: distance
    });
    
    // Limiter le nombre de points
    if (distanceHistory.length > CONFIG.distanceChartMaxPoints) {
        distanceHistory.shift();
    }
    
    // Mettre à jour le graphique
    updateDistanceChart();
}

// Mettre à jour le graphique de distance
function updateDistanceChart() {
    if (!distanceChart) return;
    
    // Extraire les données
    const labels = distanceHistory.map(item => item.time);
    const data = distanceHistory.map(item => item.value);
    
    // Mettre à jour le graphique
    distanceChart.data.labels = labels;
    distanceChart.data.datasets[0].data = data;
    distanceChart.update();
}

// Définir le mode (manuel ou automatique)
function setMode(mode) {
    autoMode = mode === 'auto';
    
    // Mettre à jour les boutons
    elements.manualModeBtn.className = autoMode ? 'mode-btn' : 'mode-btn active';
    elements.autoModeBtn.className = autoMode ? 'mode-btn active' : 'mode-btn';
    
    // Envoyer la commande au serveur
    sendCommand('set_mode', { mode: mode });
    
    // Ajouter au journal
    addLogEntry(`Mode ${mode === 'auto' ? 'automatique' : 'manuel'} activé`, 'info');
}

// Envoyer une commande au robot
function sendCommand(command, extraData = {}) {
    if (!selectedClientId) {
        addLogEntry('Aucun robot sélectionné', 'error');
        return;
    }
    
    let commandType, commandData;
    
    // Déterminer le type de commande et les données à envoyer
    switch (command) {
        case 'forward':
        case 'backward':
        case 'turn_left':
        case 'turn_right':
        case 'stand':
        case 'sit':
            commandType = 'robot_action';
            commandData = {
                action: command,
                speed: 300
            };
            break;
            
        case 'aggressive_mode':
            commandType = 'speak';
            commandData = {
                sound: 'growl',
                volume: 100
            };
            // Également définir le mode RGB
            sendCommand('set_rgb', { mode: 'boom', color: 'red', delay: 0.01 });
            break;
            
        case 'bark':
            commandType = 'speak';
            commandData = {
                sound: 'bark',
                volume: 100
            };
            break;
            
        case 'set_mode':
            commandType = 'set_mode';
            commandData = extraData;
            break;
            
        case 'set_rgb':
            commandType = 'rgb_control';
            commandData = extraData;
            break;
            
        default:
            addLogEntry(`Commande inconnue: ${command}`, 'error');
            return;
    }
    
    // Préparer les données à envoyer
    const data = {
        client_id: selectedClientId,
        command_type: commandType,
        data: commandData
    };
    
    // Envoyer la commande au serveur
    fetch(`/client/${selectedClientId}/command`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            addLogEntry(`Commande ${command} envoyée`, 'success');
        } else {
            addLogEntry(`Erreur: ${result.message}`, 'error');
        }
    })
    .catch(error => {
        addLogEntry(`Erreur lors de l'envoi de la commande: ${error.message}`, 'error');
    });
}

// Définir les effets lumineux RGB
function setRgbLight() {
    const mode = elements.lightMode.value;
    const color = elements.lightColor.value;
    
    sendCommand('set_rgb', {
        mode: mode,
        color: color,
        delay: mode === 'boom' ? 0.01 : 0.1
    });
    
    addLogEntry(`Lumières RGB définies: ${mode} ${color}`, 'info');
}

// Ajouter une entrée au journal d'activité
function addLogEntry(message, type = 'info') {
    const logContainer = elements.activityLog;
    const timestamp = new Date().toLocaleTimeString();
    
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    
    const timeSpan = document.createElement('span');
    timeSpan.className = 'log-time';
    timeSpan.textContent = timestamp;
    
    const messageSpan = document.createElement('span');
    messageSpan.className = 'log-message';
    messageSpan.textContent = message;
    
    logEntry.appendChild(timeSpan);
    logEntry.appendChild(messageSpan);
    
    logContainer.appendChild(logEntry);
    
    // Défiler vers le bas
    logContainer.scrollTop = logContainer.scrollHeight;
    
    // Limiter le nombre d'entrées
    const maxEntries = 100;
    while (logContainer.children.length > maxEntries) {
        logContainer.removeChild(logContainer.firstChild);
    }
}

// Formater une durée en secondes en chaîne lisible
function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds} sec`;
    } else if (seconds < 3600) {
        const minutes = Math.floor(seconds / 60);
        return `${minutes} min ${seconds % 60} sec`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours} h ${minutes} min`;
    }
}

// Initialiser l'interface au chargement de la page
document.addEventListener('DOMContentLoaded', initializeUI); 