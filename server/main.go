package main

import (
	"database/sql"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	_ "modernc.org/sqlite"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

type Player struct {
	ID             string    `json:"id"`
	Username       string    `json:"username"`
	X              float64   `json:"x"`
	Y              float64   `json:"y"`
	Direction      string    `json:"direction"`
	Moving         bool      `json:"moving"`
	Attacking      bool      `json:"attacking"`
	Hurt           bool      `json:"hurt"`
	Dead           bool      `json:"dead"`
	Health         int       `json:"health"`
	MaxHealth      int       `json:"max_health"`
	Level          int       `json:"level"`
	Exp            int       `json:"exp"`
	ExpToNextLevel int       `json:"exp_to_next_level"`
	Damage         int       `json:"damage"`
	IP             string    `json:"ip"`
	IsAdmin        bool      `json:"is_admin"`
	Visible        bool      `json:"visible"`
	LastUpdate     time.Time `-`
	LastAttack     time.Time `-`
	LastHurt       time.Time `-`
}

type Mob struct {
	ID         string    `json:"id"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	Direction  string    `json:"direction"`
	Health     int       `json:"health"`
	MaxHealth  int       `json:"max_health"`
	ExpReward  int       `json:"exp_reward"`
	LastAttack time.Time `-`
	LastUpdate time.Time `-`
}

type Projectile struct {
	ID         string    `json:"id"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	DX         float64   `json:"dx"`
	DY         float64   `json:"dy"`
	OwnerID    string    `json:"owner_id"`
	OwnerType  string    `json:"owner_type"`
	Damage     int       `json:"damage"`
	LastUpdate time.Time `-`
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
	Type    string  `json:"type"`
	Left    bool    `json:"left,omitempty"`
	Right   bool    `json:"right,omitempty"`
	Up      bool    `json:"up,omitempty"`
	Down    bool    `json:"down,omitempty"`
	Attack  bool    `json:"attack,omitempty"`
	Chat    string  `json:"chat,omitempty"`
	Target  string  `json:"target,omitempty"`
	TargetX float64 `json:"target_x,omitempty"`
	TargetY float64 `json:"target_y,omitempty"`
	Token   string  `json:"token,omitempty"`
}

type ServerMessage struct {
	Type        string                 `json:"type"`
	Status      string                 `json:"status,omitempty"`
	CID         string                 `json:"cid,omitempty"`
	Players     map[string]interface{} `json:"Players,omitempty"`
	Mobs        map[string]interface{} `json:"Mobs,omitempty"`
	Projectiles map[string]interface{} `json:"Projectiles,omitempty"`
	ServerTime  int64                  `json:"server_time,omitempty"`
	ChatHistory []ChatMessage          `json:"chat_history,omitempty"`
	LevelUp     *LevelUpEvent          `json:"level_up,omitempty"`
}

type LevelUpEvent struct {
	PlayerID string `json:"player_id"`
	Level    int    `json:"level"`
}

type User struct {
	Username string `json:"username"`
	Password string `json:"password"`
	IsAdmin  bool   `json:"is_admin"`
}

type RegisterRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type AuthResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	Token   string `json:"token,omitempty"`
}

type UsersData struct {
	Banned     []string `json:"banned"`
	Admins     []string `json:"admins"`
	Registered []User   `json:"registered"`
}

type UpdateResponse struct {
	UpdateAvailable bool   `json:"update_available"`
	LatestVersion   string `json:"latest_version"`
	CurrentVersion  string `json:"current_version,omitempty"`
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
	usersData   UsersData
	jwtSecret   []byte
	db          *sql.DB
	rng         = rand.New(rand.NewSource(time.Now().UnixNano()))

	connectionCounts    = make(map[string]int)
	connCountMutex      = sync.Mutex{}
	maxConnectionsPerIP = 3

	maxChatHistoryLength = 200
	maxChatMessageLength = 500
)

const (
	WIDTH             = 1920
	HEIGHT            = 1080
	MAP_WIDTH         = 10000
	MAP_HEIGHT        = 10000
	PLAYER_SPEED      = 5
	MOB_SPEED         = 2
	PROJECTILE_SPEED  = 10
	UPDATE_ZIP_PATH   = "./update.zip"
	CHUNK_SIZE        = 8192
	BASE_EXP_TO_LEVEL = 100
	EXP_PER_MOB       = 25
	EXP_MULTIPLIER    = 1.5
)

func init() {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		log.Fatal("КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения JWT_SECRET не установлена!")
	}
	jwtSecret = []byte(secret)
}

func initMobs() {
	for i := 0; i < 5; i++ {
		spawnRandomMob()
	}
}

func spawnRandomMob() {
	id := fmt.Sprintf("mob_%d", nextMobID)
	nextMobID++
	mobs[id] = &Mob{
		ID:         id,
		X:          rng.Float64() * MAP_WIDTH,
		Y:          rng.Float64() * MAP_HEIGHT,
		Direction:  "down",
		Health:     100,
		MaxHealth:  100,
		ExpReward:  EXP_PER_MOB,
		LastAttack: time.Now(),
		LastUpdate: time.Now(),
	}
}

func calculateExpToNextLevel(level int) int {
	return int(float64(BASE_EXP_TO_LEVEL) * math.Pow(EXP_MULTIPLIER, float64(level-1)))
}

func levelUpPlayer(player *Player) {
	player.Level++
	player.MaxHealth += 10
	player.Health = player.MaxHealth
	player.Damage += 5
	player.ExpToNextLevel = calculateExpToNextLevel(player.Level)

	log.Printf("Игрок %s повысил уровень до %d! HP: %d, Урон: %d",
		player.Username, player.Level, player.MaxHealth, player.Damage)

	savePlayerProgress(player)
}

func addExperience(player *Player, amount int) {
	player.Exp += amount
	log.Printf("Игрок %s получил %d опыта. Всего: %d/%d",
		player.Username, amount, player.Exp, player.ExpToNextLevel)

	for player.Exp >= player.ExpToNextLevel {
		player.Exp -= player.ExpToNextLevel
		levelUpPlayer(player)
	}
}

func savePlayerProgress(player *Player) {
	if player.Username == "" {
		return
	}
	_, err := db.Exec(`
		INSERT INTO players (username, level, health, max_health, damage, exp, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
		ON CONFLICT(username) DO UPDATE SET
			level = excluded.level,
			health = excluded.health,
			max_health = excluded.max_health,
			damage = excluded.damage,
			exp = excluded.exp,
			updated_at = excluded.updated_at
	`, player.Username, player.Level, player.Health, player.MaxHealth, player.Damage, player.Exp)

	if err != nil {
		log.Printf("Ошибка сохранения прогресса игрока %s: %v", player.Username, err)
	}
}

func loadPlayerProgress(player *Player) {
	if player.Username == "" {
		player.Level = 1
		player.Health = 100
		player.MaxHealth = 100
		player.Damage = 10
		player.Exp = 0
		player.ExpToNextLevel = BASE_EXP_TO_LEVEL
		return
	}

	var level, health, maxHealth, damage, exp int
	err := db.QueryRow(`
		SELECT level, health, max_health, damage, exp 
		FROM players 
		WHERE username = ?
	`, player.Username).Scan(&level, &health, &maxHealth, &damage, &exp)

	if err == nil {
		player.Level = level
		player.Health = health
		player.MaxHealth = maxHealth
		player.Damage = damage
		player.Exp = exp
		player.ExpToNextLevel = calculateExpToNextLevel(level)
		log.Printf("Загружен прогресс игрока %s: LVL %d, EXP %d/%d",
			player.Username, level, exp, player.ExpToNextLevel)
	} else {
		player.Level = 1
		player.Health = 100
		player.MaxHealth = 100
		player.Damage = 10
		player.Exp = 0
		player.ExpToNextLevel = BASE_EXP_TO_LEVEL
	}
}

func getLatestVersion() string {
	var version string
	err := db.QueryRow("SELECT value FROM app_settings WHERE key = 'latest_version'").Scan(&version)
	if err != nil {
		log.Printf("Ошибка получения версии из БД: %v, используем версию по умолчанию", err)
		return "1.0.0"
	}
	return version
}

func handleCommand(cid string, commandStr string, isAdmin bool) map[string]string {
	if !isAdmin {
		return map[string]string{"error": "Только администратор может выполнять команды."}
	}

	parts := strings.Fields(strings.TrimSpace(commandStr))
	if len(parts) == 0 {
		return map[string]string{"error": "Неверный синтаксис команды."}
	}

	cmd := strings.ToLower(parts[0])
	args := parts[1:]

	switch cmd {
	case "/ban":
		if len(args) < 1 {
			return map[string]string{"message": "Использование: /ban <имя_пользователя> [причина]"}
		}
		targetUsername := args[0]
		reason := "Нарушение правил"
		if len(args) > 1 {
			reason = strings.Join(args[1:], " ")
		}

		mutex.Lock()
		var targetCID string
		var targetIP string
		for c, p := range players {
			if p.Username == targetUsername {
				targetCID = c
				targetIP = p.IP
				break
			}
		}
		if targetCID != "" {
			delete(players, targetCID)
			if conn, exists := connections[targetCID]; exists {
				conn.Close()
				delete(connections, targetCID)
			}
		}
		mutex.Unlock()

		if targetCID != "" {
			log.Printf("Блокировка игрока %s (%s) - Причина: %s", targetUsername, targetIP, reason)
			return map[string]string{"message": fmt.Sprintf("Игрок %s заблокирован.", targetUsername)}
		}
		return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}

	case "/kick":
		if len(args) < 1 {
			return map[string]string{"message": "Использование: /kick <имя_пользователя> [причина]"}
		}
		targetUsername := args[0]
		reason := "Кикнут администратором"
		if len(args) > 1 {
			reason = strings.Join(args[1:], " ")
		}

		mutex.Lock()
		var targetCID string
		var targetIP string
		for c, p := range players {
			if p.Username == targetUsername {
				targetCID = c
				targetIP = p.IP
				break
			}
		}
		if targetCID != "" {
			delete(players, targetCID)
			if conn, exists := connections[targetCID]; exists {
				conn.Close()
				delete(connections, targetCID)
			}
		}
		mutex.Unlock()

		if targetCID != "" {
			log.Printf("Кик игрока %s (%s) - Причина: %s", targetUsername, targetIP, reason)
			return map[string]string{"message": fmt.Sprintf("Игрок %s кикнут.", targetUsername)}
		}
		return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}

	case "/list":
		mutex.RLock()
		playerList := []string{}
		for pid, p := range players {
			username := p.Username
			if username == "" {
				username = pid[:8]
			}
			playerList = append(playerList, fmt.Sprintf("%s (LVL:%d) на позиции (%.0f, %.0f)",
				username, p.Level, p.X, p.Y))
		}
		mutex.RUnlock()

		if len(playerList) == 0 {
			return map[string]string{"message": "Нет игроков онлайн."}
		}
		return map[string]string{"message": "Игроки онлайн:\n" + strings.Join(playerList, "\n")}

	case "/clear":
		mutex.Lock()
		if len(chatHistory) > 0 {
			chatHistory = []ChatMessage{}
			mutex.Unlock()
			return map[string]string{"message": "История чата очищена."}
		}
		mutex.Unlock()
		return map[string]string{"message": "История чата уже пуста."}

	case "/restart":
		if len(args) == 0 {
			return map[string]string{"message": "Использование: /restart <секунды>"}
		}
		seconds, err := strconv.Atoi(args[0])
		if err != nil {
			return map[string]string{"error": "Неверное количество секунд."}
		}
		log.Printf("Сервер перезапустится через %d секунд...", seconds)
		go func() {
			time.Sleep(time.Duration(seconds) * time.Second)
			log.Println("Перезапуск сервера...")
			os.Exit(0)
		}()
		return map[string]string{"message": fmt.Sprintf("Сервер перезапустится через %d секунд.", seconds)}

	case "/stop":
		if len(args) == 0 {
			return map[string]string{"message": "Использование: /stop <секунды>"}
		}
		seconds, err := strconv.Atoi(args[0])
		if err != nil {
			return map[string]string{"error": "Неверное количество секунд."}
		}
		log.Printf("Сервер остановится через %d секунд...", seconds)
		go func() {
			time.Sleep(time.Duration(seconds) * time.Second)
			log.Println("Остановка сервера...")
			os.Exit(0)
		}()
		return map[string]string{"message": fmt.Sprintf("Сервер остановится через %d секунд.", seconds)}

	case "/stats":
		mutex.RLock()
		playerCount := len(players)
		connCount := len(connections)
		mutex.RUnlock()

		uptime := time.Since(startTime).Seconds()
		return map[string]string{"message": fmt.Sprintf("Статистика сервера:\nИгроки онлайн: %d\nВсего клиентов: %d\nВремя работы: %.0f секунд", playerCount, connCount, uptime)}

	case "/level_up":
		if len(args) < 2 {
			return map[string]string{"message": "Использование: /level_up <имя_пользователя> <уровень>"}
		}
		targetUsername := args[0]
		level, err := strconv.Atoi(args[1])
		if err != nil {
			return map[string]string{"error": "Неверный уровень."}
		}

		mutex.Lock()
		var targetPlayer *Player
		for _, p := range players {
			if p.Username == targetUsername {
				targetPlayer = p
				break
			}
		}
		if targetPlayer != nil {
			targetPlayer.Level = level
			targetPlayer.ExpToNextLevel = calculateExpToNextLevel(level)
			savePlayerProgress(targetPlayer)
			mutex.Unlock()
			return map[string]string{"message": fmt.Sprintf("Уровень игрока %s обновлен до %d.", targetUsername, level)}
		}
		mutex.Unlock()
		return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}

	case "/add_exp":
		if len(args) < 2 {
			return map[string]string{"message": "Использование: /add_exp <имя_пользователя> <опыт>"}
		}
		targetUsername := args[0]
		exp, err := strconv.Atoi(args[1])
		if err != nil {
			return map[string]string{"error": "Неверное количество опыта."}
		}

		mutex.Lock()
		var targetPlayer *Player
		for _, p := range players {
			if p.Username == targetUsername {
				targetPlayer = p
				break
			}
		}
		if targetPlayer != nil {
			addExperience(targetPlayer, exp)
			mutex.Unlock()
			return map[string]string{"message": fmt.Sprintf("Игроку %s добавлено %d опыта.", targetUsername, exp)}
		}
		mutex.Unlock()
		return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}

	case "/version":
		return map[string]string{"message": fmt.Sprintf("Версия сервера: %s", currentVersion)}

	case "/help":
		helpText := []string{
			"/ban <имя_пользователя> [причина]",
			"/kick <имя_пользователя> [причина]",
			"/list",
			"/stats",
			"/version",
			"/help",
			"/clear",
			"/restart",
			"/stop",
			"/level_up <имя_пользователя> <уровень>",
			"/add_exp <имя_пользователя> <опыт>",
		}
		return map[string]string{"message": strings.Join(helpText, "\n")}

	default:
		return map[string]string{"error": fmt.Sprintf("Неизвестная команда: %s", cmd)}
	}
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	ip := strings.Split(r.RemoteAddr, ":")[0]

	connCountMutex.Lock()
	if connectionCounts[ip] >= maxConnectionsPerIP {
		connCountMutex.Unlock()
		http.Error(w, "Too many connections from this IP", http.StatusTooManyRequests)
		return
	}
	connectionCounts[ip]++
	connCountMutex.Unlock()

	defer func() {
		connCountMutex.Lock()
		connectionCounts[ip]--
		connCountMutex.Unlock()
	}()

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Ошибка обновления:", err)
		return
	}
	defer conn.Close()

	isAdmin := false
	cid := uuid.New().String()

	mutex.Lock()
	players[cid] = &Player{
		ID:             cid,
		X:              float64(WIDTH / 2),
		Y:              float64(HEIGHT - 100),
		Direction:      "down",
		Moving:         false,
		Hurt:           false,
		Dead:           false,
		Health:         100,
		MaxHealth:      100,
		Level:          1,
		Exp:            0,
		ExpToNextLevel: BASE_EXP_TO_LEVEL,
		Damage:         10,
		IP:             ip,
		IsAdmin:        isAdmin,
		Visible:        true,
		LastUpdate:     time.Now(),
		LastAttack:     time.Now(),
		LastHurt:       time.Now(),
	}
	connections[cid] = conn
	mutex.Unlock()

	log.Printf("Игрок подключен: %s (%s, админ: %t)", cid, ip, isAdmin)

	statusMsg := ServerMessage{Type: "status", Status: "ok", CID: cid}
	if isAdmin {
		statusMsg.Status = "admin"
	}
	conn.WriteJSON(statusMsg)

	for {
		var msg ClientMessage
		err := conn.ReadJSON(&msg)
		if err != nil {
			log.Println("Ошибка чтения:", err)
			break
		}

		mutex.Lock()
		player := players[cid]
		if player == nil {
			mutex.Unlock()
			continue
		}

		switch msg.Type {
		case "handshake":
			if msg.Token != "" {
				username, err := validateJWT(msg.Token)
				if err == nil {
					player.Username = username
					for _, admin := range usersData.Admins {
						if admin == username {
							player.IsAdmin = true
							break
						}
					}
					for _, user := range usersData.Registered {
						if user.Username == username && user.IsAdmin {
							player.IsAdmin = true
							break
						}
					}
					isAdmin = player.IsAdmin

					loadPlayerProgress(player)
				}
			}

		case "input":
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

			if msg.Attack {
				if time.Since(player.LastAttack) > 600*time.Millisecond {
					projDX := 0.0
					projDY := 0.0

					if msg.TargetX != 0 || msg.TargetY != 0 {
						tdx := msg.TargetX - player.X
						tdy := msg.TargetY - player.Y
						distance := math.Sqrt(tdx*tdx + tdy*tdy)
						if distance > 0 {
							projDX = tdx / distance
							projDY = tdy / distance
						}
					}

					if projDX == 0 && projDY == 0 {
						switch direction {
						case "up":
							projDY = -1
						case "down":
							projDY = 1
						case "left":
							projDX = -1
						case "right":
							projDX = 1
						}
					}

					projID := fmt.Sprintf("proj_%d", nextProjID)
					nextProjID++
					projectiles[projID] = &Projectile{
						ID:         projID,
						X:          player.X,
						Y:          player.Y,
						DX:         projDX * PROJECTILE_SPEED,
						DY:         projDY * PROJECTILE_SPEED,
						OwnerID:    cid,
						OwnerType:  "player",
						Damage:     player.Damage,
						LastUpdate: time.Now(),
					}
					player.LastAttack = time.Now()
				}
			}

			if msg.Chat != "" {
				if len(msg.Chat) > maxChatMessageLength {
					mutex.Unlock()
					continue
				}

				message := strings.TrimSpace(msg.Chat)
				if strings.HasPrefix(message, "/") && isAdmin {
					mutex.Unlock()

					response := handleCommand(cid, message, isAdmin)

					mutex.Lock()
					if response["message"] != "" {
						chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: response["message"]})
					}
					if response["error"] != "" {
						chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: "Ошибка: " + response["error"]})
					}
				} else {
					username := player.Username
					if username == "" {
						username = cid[:8]
					}
					chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: fmt.Sprintf("[%s]: %s", username, message)})
				}

				if len(chatHistory) > maxChatHistoryLength {
					chatHistory = chatHistory[len(chatHistory)-maxChatHistoryLength:]
				}
			}

		case "pvp_hit":
			if msg.Target != "" {
				if targetPlayer, exists := players[msg.Target]; exists {
					if time.Since(targetPlayer.LastHurt) > 500*time.Millisecond {
						distance := math.Sqrt(math.Pow(player.X-targetPlayer.X, 2) + math.Pow(player.Y-targetPlayer.Y, 2))
						if distance < 50 {
							targetPlayer.Health -= player.Damage
							targetPlayer.Hurt = true
							targetPlayer.LastHurt = time.Now()
							if targetPlayer.Health <= 0 {
								targetPlayer.Dead = true
								targetPlayer.Health = 0
								go respawnPlayer(msg.Target)
							}
						}
					}
				}
			}
		}
		mutex.Unlock()
	}

	mutex.Lock()
	if player, exists := players[cid]; exists {
		savePlayerProgress(player)
	}
	delete(players, cid)
	delete(connections, cid)
	mutex.Unlock()
	log.Printf("Игрок отключен: %s", cid)
}

func respawnPlayer(cid string) {
	time.Sleep(3 * time.Second)

	mutex.Lock()
	defer mutex.Unlock()

	player, exists := players[cid]
	if !exists {
		return
	}

	player.X = float64(WIDTH / 2)
	player.Y = float64(HEIGHT - 100)
	player.Health = player.MaxHealth
	player.Dead = false
	player.Hurt = false
	log.Printf("Игрок %s респавнился", cid)
}

func gameLoop() {
	ticker := time.NewTicker(16 * time.Millisecond)
	defer ticker.Stop()

	for range ticker.C {
		mutex.Lock()

		currentTime := time.Now()

		for _, mob := range mobs {
			var nearestPlayer *Player
			minDistance := math.Inf(1)
			for _, player := range players {
				distance := math.Sqrt(math.Pow(player.X-mob.X, 2) + math.Pow(player.Y-mob.Y, 2))
				if distance < minDistance {
					minDistance = distance
					nearestPlayer = player
				}
			}

			if nearestPlayer != nil && minDistance > 0 {
				dx := nearestPlayer.X - mob.X
				dy := nearestPlayer.Y - mob.Y
				mob.X += (dx / minDistance) * MOB_SPEED
				mob.Y += (dy / minDistance) * MOB_SPEED
				mob.X = math.Max(0, math.Min(mob.X, MAP_WIDTH))
				mob.Y = math.Max(0, math.Min(mob.Y, MAP_HEIGHT))
				mob.LastUpdate = currentTime
			}

			if nearestPlayer != nil && minDistance < 200 {
				if time.Since(mob.LastAttack) > 1000*time.Millisecond {
					dx := nearestPlayer.X - mob.X
					dy := nearestPlayer.Y - mob.Y
					distance := math.Sqrt(dx*dx + dy*dy)
					if distance > 0 {
						dx /= distance
						dy /= distance
					}
					projID := fmt.Sprintf("mob_proj_%d", nextProjID)
					nextProjID++
					projectiles[projID] = &Projectile{
						ID:         projID,
						X:          mob.X,
						Y:          mob.Y,
						DX:         dx * PROJECTILE_SPEED,
						DY:         dy * PROJECTILE_SPEED,
						OwnerID:    mob.ID,
						OwnerType:  "mob",
						Damage:     20,
						LastUpdate: currentTime,
					}
					mob.LastAttack = currentTime
				}
			}
		}

		var projectilesToDelete []string
		var mobsToDelete []string

		for id, proj := range projectiles {
			proj.X += proj.DX
			proj.Y += proj.DY
			if proj.X < 0 || proj.X > MAP_WIDTH || proj.Y < 0 || proj.Y > MAP_HEIGHT {
				projectilesToDelete = append(projectilesToDelete, id)
				continue
			}

			if proj.OwnerType == "player" {
				for mobID, mob := range mobs {
					if math.Abs(proj.X-mob.X) < 32 && math.Abs(proj.Y-mob.Y) < 32 {
						mob.Health -= proj.Damage
						projectilesToDelete = append(projectilesToDelete, id)

						if mob.Health <= 0 {
							if player, exists := players[proj.OwnerID]; exists {
								addExperience(player, mob.ExpReward)
								log.Printf("Игрок %s убил моба %s и получил %d опыта",
									player.Username, mobID, mob.ExpReward)
							}
							mobsToDelete = append(mobsToDelete, mobID)
						}
						break
					}
				}
			}

			if proj.OwnerType == "mob" {
				for playerID, player := range players {
					if math.Abs(proj.X-player.X) < 32 && math.Abs(proj.Y-player.Y) < 32 {
						log.Printf("Снаряд (ID: %s) попал в игрока (ID: %s). Нанесено %d урона.",
							proj.ID, playerID, proj.Damage)
						player.Health -= proj.Damage
						player.Hurt = true
						player.LastHurt = currentTime
						projectilesToDelete = append(projectilesToDelete, id)

						if player.Health <= 0 {
							player.Dead = true
							player.Health = 0
							go respawnPlayer(playerID)
							log.Printf("Игрок (ID: %s) был убит снарядом (ID: %s).", playerID, proj.ID)
						}
						break
					}
				}
			}
		}

		for _, id := range projectilesToDelete {
			delete(projectiles, id)
		}
		for _, id := range mobsToDelete {
			delete(mobs, id)
			spawnRandomMob()
		}

		playersState := make(map[string]interface{})
		for id, p := range players {
			playersState[id] = map[string]interface{}{
				"id":                p.ID,
				"x":                 p.X,
				"y":                 p.Y,
				"direction":         p.Direction,
				"moving":            p.Moving,
				"attacking":         p.Attacking,
				"hurt":              p.Hurt,
				"dead":              p.Dead,
				"health":            p.Health,
				"max_health":        p.MaxHealth,
				"level":             p.Level,
				"exp":               p.Exp,
				"exp_to_next_level": p.ExpToNextLevel,
				"damage":            p.Damage,
			}
		}

		mobsState := make(map[string]interface{})
		for id, m := range mobs {
			mobsState[id] = map[string]interface{}{
				"id":         m.ID,
				"x":          m.X,
				"y":          m.Y,
				"direction":  m.Direction,
				"health":     m.Health,
				"max_health": m.MaxHealth,
			}
		}

		projectilesState := make(map[string]interface{})
		for id, p := range projectiles {
			projectilesState[id] = map[string]interface{}{
				"id": p.ID,
				"x":  p.X,
				"y":  p.Y,
			}
		}

		chatCopy := make([]ChatMessage, len(chatHistory))
		copy(chatCopy, chatHistory)

		stateMsg := ServerMessage{
			Type:        "state",
			Players:     playersState,
			Mobs:        mobsState,
			Projectiles: projectilesState,
			ServerTime:  int64(currentTime.Unix()),
			ChatHistory: chatCopy,
		}

		connsCopy := make([]*websocket.Conn, 0, len(connections))
		for _, conn := range connections {
			connsCopy = append(connsCopy, conn)
		}

		mutex.Unlock()

		for _, conn := range connsCopy {
			go func(c *websocket.Conn) {
				c.WriteJSON(stateMsg)
			}(conn)
		}
	}
}

func createTables() {
	_, err := db.Exec(`
	CREATE TABLE IF NOT EXISTS users (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		username TEXT UNIQUE NOT NULL,
		password TEXT NOT NULL,
		is_admin INTEGER DEFAULT 0
	)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы users:", err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS admins (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		username TEXT UNIQUE NOT NULL
	)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы admins:", err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS banned (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		username TEXT UNIQUE NOT NULL
	)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы banned:", err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS players (
		username TEXT PRIMARY KEY,
		health INTEGER DEFAULT 100,
		max_health INTEGER DEFAULT 100,
		level INTEGER DEFAULT 1,
		exp INTEGER DEFAULT 0,
		damage INTEGER DEFAULT 10,
		updated_at TEXT DEFAULT (datetime('now'))
	)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы players:", err)
	}

	_, err = db.Exec(`
	CREATE TABLE IF NOT EXISTS app_settings (
		key TEXT PRIMARY KEY,
		value TEXT NOT NULL,
		updated_at TEXT DEFAULT (datetime('now'))
	)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы app_settings:", err)
	}

	_, err = db.Exec(`
	INSERT OR IGNORE INTO app_settings (key, value)
	VALUES ('latest_version', '1.0.0')
	`)
	if err != nil {
		log.Printf("Ошибка инициализации версии: %v", err)
	}

	log.Println("Таблицы созданы успешно")
}

func main() {
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		databaseURL = "file:game.db?cache=shared&mode=rwc"
	}

	var err error
	db, err = sql.Open("sqlite", databaseURL)
	if err != nil {
		log.Fatal("Ошибка подключения к БД:", err)
	}
	defer db.Close()

	err = db.Ping()
	if err != nil {
		log.Fatal("Ошибка ping к БД:", err)
	}

	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	db.SetConnMaxLifetime(0)

	createTables()

	currentVersion = getLatestVersion()
	log.Printf("Текущая версия сервера: %s", currentVersion)

	loadUsers()
	initMobs()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/ws", wsHandler)
	http.HandleFunc("/register", registerHandler)
	http.HandleFunc("/login", loginHandler)
	http.HandleFunc("/check_update", checkUpdateHandler)
	http.HandleFunc("/download_update", downloadUpdateHandler)
	http.HandleFunc("/admin/backup", adminBackupHandler)

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprintf(w, `
<!DOCTYPE html>
<html>
<head><title>Game Server</title></head>
<body>
<h1>Game Server v%s</h1>
<p>Сервер запущен и работает</p>
<ul>
<li><a href="/check_update?version=1.0.0">Проверить обновления</a></li>
<li>WebSocket: /ws</li>
<li>Регистрация: /register</li>
<li>Вход: /login</li>
</ul>
</body>
</html>
			`, currentVersion)
		}
	})

	go gameLoop()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		log.Println("Получен сигнал завершения, сохраняем прогресс всех игроков...")

		mutex.Lock()
		for _, player := range players {
			savePlayerProgress(player)
		}
		mutex.Unlock()

		log.Println("Прогресс сохранён. Завершение работы.")
		os.Exit(0)
	}()

	log.Printf("Запуск сервера на порту %s...", port)
	log.Printf("Текущая версия: %s", currentVersion)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
