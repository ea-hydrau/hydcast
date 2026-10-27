const map = L.map('map').setView([48.85, 2.35], 9);
let rainChart = null;

// Fond de carte OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap'
}).addTo(map);

// Charger les bassins versants depuis l'API Python
fetch('http://127.0.0.1:8000/api/watersheds')
    .then(res => res.json())
    .then(data => {
        L.geoJSON(data, {
            style: { color: '#2b5c8f', weight: 2, fillOpacity: 0.3 },
            onEachFeature: (feature, layer) => {
                layer.on('click', (e) => {
                    const lat = e.latlng.lat;
                    const lon = e.latlng.lng;
                    document.getElementById('info').innerHTML = `<b>${feature.properties.nom}</b><br>Coordonnées cliquées : ${lat.toFixed(3)}, ${lon.toFixed(3)}`;
                    loadRainData(lat, lon);
                });
            }
        }).addTo(map);
    });

// Charger la pluie et construire le graphique
function loadRainData(lat, lon) {
    fetch(`http://127.0.0.1:8000/api/weather/rain?lat=${lat}&lon=${lon}`)
        .then(res => res.json())
        .then(data => {
            const times = data.hourly.time;
            const precipitation = data.hourly.precipitation;

            const ctx = document.getElementById('rainChart').getContext('2d');
            if (rainChart) rainChart.destroy(); // Réinitialiser le graphique existant

            rainChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: times,
                    datasets: [{
                        label: 'Précipitations (mm)',
                        data: precipitation,
                        backgroundColor: 'rgba(54, 162, 235, 0.6)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: { display: false }, // Masqué pour plus de clarté
                        y: { title: { display: true, text: 'Pluie (mm)' } }
                    }
                }
            });
        });
}
