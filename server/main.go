package main

import (
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins for simplicity
	},
}

type Player struct {
	ID         string    `json:"id"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	Direction  string    `json:"direction"`
	Moving     bool      `json:"moving"`
	Attacking  bool      `json:"attacking"`
	IP         string    `json:"ip"`
	IsAdmin    bool      `json:"is_admin"`
	Visible    bool      `json:"visible"`
	LastUpdate time.Time `json:"-"`
	LastAttack time.Time `json:"-"`
}

type Mob struct {
	ID        string    `json:"id"`
	X         float64   `json:"x"`
	Y         float64   `json:"y"`
	Direction string    `json:"direction"`
	Health    int       `json:"health"`
	LastUpdate time.Time `json:"-"`
}

type Projectile struct {
	ID        string    `json:"id"`
	X         float64   `json:"x"`
	Y         float64   `json:"y"`
	DX        float64   `json:"dx"`
	DY        float64   `json:"dy"`
	OwnerID   string    `json:"owner_id"`
	LastUpdate time.Time `json:"-"`
}

type GameState struct {
	Players     map[string]Player     `json:"Players"`
	Mobs        map[string]Mob        `json:"Mobs"`
	Projectiles map[string]Projectile `json:"Projectiles"`
	ServerTime  int64                 `json:"server_time"`
	ChatHistory []ChatMessage         `json:"chat_history"`
}

type ChatMessage struct {
	Sender  int    `json:"sender"`
	Message string `json:"message"`
}

type ClientMessage struct {
	Type   string `json:"type"`
	Left   bool   `json:"left,omitempty"`
	Right  bool   `json:"right,omitempty"`
	Up     bool   `json:"up,omitempty"`
	Down   bool   `json:"down,omitempty"`
	Attack bool   `json:"attack,omitempty"`
	Chat   string `json:"chat,omitempty"`
}

type ServerMessage struct {
	Type       string                 `json:"type"`
	Status     string                 `json:"status,omitempty"`
	CID        string                 `json:"cid,omitempty"`
	Players    map[string]interface{} `json:"Players,omitempty"`
	Mobs       map[string]interface{} `json:"Mobs,omitempty"`
	Projectiles map[string]interface{} `json:"Projectiles,omitempty"`
	ServerTime int64                  `json:"server_time,omitempty"`
	ChatHistory []ChatMessage         `json:"chat_history,omitempty"`
}

var (
	players     = make(map[string]*Player)
	mobs        = make(map[string]*Mob)
	projectiles = make(map[string]*Projectile)
	connections = make(map[string]*websocket.Conn)
	chatHistory = []ChatMessage{}
	mutex       = sync.RWMutex{}
	nextMobID   = 0
	nextProjID  = 0
	startTime   = time.Now()
	adminIPs    = []string{"192.168.1.4", "109.252.167.96", "127.0.0.1", "::1"}
)

const (
	WIDTH          = 1920
	HEIGHT         = 1080
	MAP_WIDTH      = 10000
	MAP_HEIGHT     = 10000
	PLAYER_SPEED   = 5
	MOB_SPEED      = 2
	PROJECTILE_SPEED = 10
)

func initMobs() {
	for i := 0; i < 5; i++ {
		id := fmt.Sprintf("mob_%d", nextMobID)
		nextMobID++
		mobs[id] = &Mob{
			ID:         id,
			X:          rand.Float64() * MAP_WIDTH,
			Y:          rand.Float64() * MAP_HEIGHT,
			Direction:  "down",
			Health:     100,
			LastUpdate: time.Now(),
		}
	}
}

func handleCommand(cid string, commandStr string, isAdmin bool) map[string]string {
	if !isAdmin {
		return map[string]string{"error": "Not admin"}
	}

	parts := strings.Fields(strings.TrimSpace(commandStr))
	if len(parts) == 0 {
		return map[string]string{"error": "Invalid command"}
	}

	cmd := strings.ToLower(parts[0])
	args := parts[1:]

	switch cmd {
	case "/ban":
		if len(args) < 1 {
			return map[string]string{"message": "Usage: /ban <client_id> [reason]"}
		}
		targetCID := args[0]
		reason := "rule violation"
		if len(args) > 1 {
			reason = strings.Join(args[1:], " ")
		}
		if player, exists := players[targetCID]; exists {
			// Ban logic (simplified)
			if conn, exists := connections[targetCID]; exists {
				conn.Close()
			}
			log.Printf("Ban: %s (%s) - %s", targetCID, player.IP, reason)
			return map[string]string{"message": fmt.Sprintf("Player %s banned: %s", targetCID, reason)}
		} else {
			return map[string]string{"error": fmt.Sprintf("Player %s not found", targetCID)}
		}
	case "/kick":
		if len(args) < 1 {
			return map[string]string{"message": "Usage: /kick <client_id> [reason]"}
		}
		targetCID := args[0]
		reason := "kicked by admin"
		if len(args) > 1 {
			reason = strings.Join(args[1:], " ")
		}
		if _, exists := players[targetCID]; exists {
			if conn, exists := connections[targetCID]; exists {
				conn.Close()
			}
			log.Printf("Kick: %s - %s", targetCID, reason)
			return map[string]string{"message": fmt.Sprintf("Player %s kicked: %s", targetCID, reason)}
		} else {
			return map[string]string{"error": fmt.Sprintf("Player %s not found", targetCID)}
		}
	case "/list":
		playerList := []string{}
		for pid, p := range players {
			playerList = append(playerList, fmt.Sprintf("ID %s: %s (%.0f, %.0f)", pid, p.IP, p.X, p.Y))
		}
		if len(playerList) == 0 {
			return map[string]string{"message": "No players online"}
		}
		return map[string]string{"message": "Online players:\n" + strings.Join(playerList, "\n")}
	case "/stats":
		uptime := time.Since(startTime).Seconds()
		return map[string]string{"message": fmt.Sprintf("Server stats:\nOnline players: %d\nTotal clients: %d\nUptime: %.0f sec", len(players), len(connections), uptime)}
	case "/help":
		help := []string{
			"/ban <id> [reason] - Ban player",
			"/kick <id> [reason] - Kick player",
			"/list - List players",
			"/stats - Server stats",
			"/help - This help",
		}
		return map[string]string{"message": strings.Join(help, "\n")}
	default:
		return map[string]string{"error": fmt.Sprintf("Unknown command: %s", cmd)}
	}
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Upgrade error:", err)
		return
	}
	defer conn.Close()

	ip := r.RemoteAddr
	isAdmin := false
	for _, adminIP := range adminIPs {
		if strings.Contains(ip, adminIP) {
			isAdmin = true
			break
		}
	}

	cid := uuid.New().String()

	mutex.Lock()
	players[cid] = &Player{
		ID:         cid,
		X:          WIDTH / 2,
		Y:          HEIGHT - 100,
		Direction:  "down",
		Moving:     false,
		IP:         ip,
		IsAdmin:    isAdmin,
		Visible:    true,
		LastUpdate: time.Now(),
		LastAttack: time.Now(),
	}
	connections[cid] = conn
	mutex.Unlock()

	log.Printf("Player connected: %s (%s, admin: %t)", cid, ip, isAdmin)

	// Send status
	statusMsg := ServerMessage{Type: "status", Status: "ok", CID: cid}
	if isAdmin {
		statusMsg.Status = "admin"
	}
	conn.WriteJSON(statusMsg)

	for {
		var msg ClientMessage
		err := conn.ReadJSON(&msg)
		if err != nil {
			log.Println("Read error:", err)
			break
		}

		mutex.Lock()
		player := players[cid]
		if player == nil {
			mutex.Unlock()
			continue
		}

		switch msg.Type {
		case "input":
			// Movement
			dx := 0.0
			dy := 0.0
			if msg.Left {
				dx = -1
			} else if msg.Right {
				dx = 1
			}
			if msg.Up {
				dy = -1
			} else if msg.Down {
				dy = 1
			}

			moving := dx != 0 || dy != 0
			direction := player.Direction
			if dy < 0 {
				direction = "up"
			} else if dy > 0 {
				direction = "down"
			} else if dx < 0 {
				direction = "left"
			} else if dx > 0 {
				direction = "right"
			}

			player.X += dx * PLAYER_SPEED
			player.Y += dy * PLAYER_SPEED
			player.X = math.Max(0, math.Min(player.X, MAP_WIDTH))
			player.Y = math.Max(0, math.Min(player.Y, MAP_HEIGHT))
			player.Direction = direction
			player.Moving = moving
			player.Attacking = msg.Attack
			player.LastUpdate = time.Now()

			// Attack
			if msg.Attack {
				// Add cooldown to slow down shooting
				if time.Since(player.LastAttack) > 600*time.Millisecond {
					projID := fmt.Sprintf("proj_%d", nextProjID)
					nextProjID++
					dirX := 0.0
					dirY := 0.0
					switch direction {
					case "up":
						dirY = -1
					case "down":
						dirY = 1
					case "left":
						dirX = -1
					case "right":
						dirX = 1
					}
					projectiles[projID] = &Projectile{
						ID:         projID,
						X:          player.X,
						Y:          player.Y,
						DX:         dirX * PROJECTILE_SPEED,
						DY:         dirY * PROJECTILE_SPEED,
						OwnerID:    cid,
						LastUpdate: time.Now(),
					}
					player.LastAttack = time.Now()
				}
			}

			// Chat
			if msg.Chat != "" {
				message := strings.TrimSpace(msg.Chat)
				if strings.HasPrefix(message, "/") && isAdmin {
					response := handleCommand(cid, message, isAdmin)
					chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: response["message"]})
					if response["error"] != "" {
						chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: response["error"]})
					}
				} else {
					chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: fmt.Sprintf("ID %s: %s", cid[:8], message)})
				}
			}
		}
		mutex.Unlock()
	}

	mutex.Lock()
	delete(players, cid)
	delete(connections, cid)
	mutex.Unlock()
	log.Printf("Player disconnected: %s", cid)
}

func gameLoop() {
	ticker := time.NewTicker(16 * time.Millisecond) // ~60 FPS
	defer ticker.Stop()

	for range ticker.C {
		mutex.Lock()

		currentTime := time.Now()

		// Update mobs (simple AI)
		for _, player := range players {
			var nearestMob *Mob
			minDist := math.Inf(1)
			for _, mob := range mobs {
				dist := math.Sqrt(math.Pow(mob.X-player.X, 2) + math.Pow(mob.Y-player.Y, 2))
				if dist < minDist {
					minDist = dist
					nearestMob = mob
				}
			}
			if nearestMob != nil && minDist > 0 {
				dx := player.X - nearestMob.X
				dy := player.Y - nearestMob.Y
				nearestMob.X += (dx / minDist) * MOB_SPEED
				nearestMob.Y += (dy / minDist) * MOB_SPEED
				nearestMob.X = math.Max(0, math.Min(nearestMob.X, MAP_WIDTH))
				nearestMob.Y = math.Max(0, math.Min(nearestMob.Y, MAP_HEIGHT))
				nearestMob.LastUpdate = currentTime
			}
		}

		// Update projectiles
		for id, proj := range projectiles {
			proj.X += proj.DX
			proj.Y += proj.DY
			proj.LastUpdate = currentTime
			if proj.X < 0 || proj.X > MAP_WIDTH || proj.Y < 0 || proj.Y > MAP_HEIGHT {
				delete(projectiles, id)
			}
		}

		// Check collisions
		for projID, proj := range projectiles {
			for mobID, mob := range mobs {
				if math.Abs(proj.X-mob.X) < 32 && math.Abs(proj.Y-mob.Y) < 32 {
					mob.Health -= 10
					delete(projectiles, projID)
					if mob.Health <= 0 {
						delete(mobs, mobID)
						// Respawn mob
						newMobID := fmt.Sprintf("mob_%d", nextMobID)
						nextMobID++
						mobs[newMobID] = &Mob{
							ID:         newMobID,
							X:          rand.Float64() * MAP_WIDTH,
							Y:          rand.Float64() * MAP_HEIGHT,
							Direction:  "down",
							Health:     100,
							LastUpdate: currentTime,
						}
					}
					break
				}
			}
		}

		// Prepare state
		playersState := make(map[string]interface{})
		for id, p := range players {
			playersState[id] = map[string]interface{}{
				"id":        p.ID,
				"x":         p.X,
				"y":         p.Y,
				"direction": p.Direction,
				"moving":    p.Moving,
				"attacking": p.Attacking,
			}
		}
		mobsState := make(map[string]interface{})
		for id, m := range mobs {
			mobsState[id] = map[string]interface{}{
				"id":        m.ID,
				"x":         m.X,
				"y":         m.Y,
				"direction": m.Direction,
				"health":    m.Health,
			}
		}
		projectilesState := make(map[string]interface{})
		for id, p := range projectiles {
			projectilesState[id] = map[string]interface{}{
				"id":  p.ID,
				"x":   p.X,
				"y":   p.Y,
			}
		}

		stateMsg := ServerMessage{
			Type:        "state",
			Players:     playersState,
			Mobs:        mobsState,
			Projectiles: projectilesState,
			ServerTime:  int64(currentTime.Unix()),
			ChatHistory: chatHistory[len(chatHistory)-min(10, len(chatHistory)):],
		}

		// Broadcast
		for _, conn := range connections {
			conn.WriteJSON(stateMsg)
		}

		mutex.Unlock()
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func main() {
	rand.Seed(time.Now().UnixNano())
	initMobs()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/ws", wsHandler)
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "MOBA Server running on port %s", port)
	})

	go gameLoop()

	log.Printf("MOBA Server starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
