# TODO for Карта MOBA Game

## Server (Go)
- [x] Implement WebSocket server with Gorilla
- [x] Player management (connect/disconnect, movement)
- [x] Mob AI (move towards players)
- [x] Projectile system (shoot, move, collision with mobs)
- [x] Admin commands (/ban, /kick, /list, /stats, /help)
- [x] Chat system
- [x] Game loop broadcasting state at 60 FPS
- [x] JSON serialization with capital keys (Players, Mobs, Projectiles)

## Client (Python)
- [x] WebSocket client connection
- [x] Pygame rendering with TMX map
- [x] Simple squares for players (green self, blue others), mobs (red), projectiles (yellow)
- [x] Input handling (movement, attack with space, chat with T)
- [x] Camera following player
- [x] Chat display and input

## Deployment
- [ ] Test local connection
- [ ] Deploy server to Render/Fly.io
- [ ] Update client SERVER_URL for deployed server

## Testing
- [ ] Run server locally: `cd server && go run main.go`
- [ ] Run client locally: `cd client && python main.py`
- [ ] Test multiplayer: multiple clients connecting, moving, attacking mobs
- [ ] Test chat and admin commands
- [ ] Test collision detection and mob respawning

## Improvements
- [ ] Add more mob types and behaviors
- [ ] Implement player health and respawning
- [ ] Add items/power-ups
- [ ] Improve graphics (replace squares with sprites)
- [ ] Add sound effects
- [ ] Optimize network traffic
