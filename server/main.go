package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/dgrijalva/jwt-go"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	_ "github.com/lib/pq"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Разрешаем любые запросы для упрощения
	},
}

type Player struct {
	ID         string    `json:"id"`
	Username   string    `json:"username"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	Direction  string    `json:"direction"`
	Moving     bool      `json:"moving"`
	Attacking  bool      `json:"attacking"`
	Hurt       bool      `json:"hurt"`
	Dead       bool      `json:"dead"`
	Health     int       `json:"health"`
	Level      int       `json:"level"`
	IP         string    `json:"ip"`
	IsAdmin    bool      `json:"is_admin"`
	Visible    bool      `json:"visible"`
	LastUpdate time.Time `json:"-"`
	LastAttack time.Time `json:"-"`
	LastHurt   time.Time `json:"-"`
}

type Mob struct {
	ID         string    `json:"id"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	Direction  string    `json:"direction"`
	Health     int       `json:"health"`
	LastUpdate time.Time `json:"-"`
}

type Projectile struct {
	ID         string    `json:"id"`
	X          float64   `json:"x"`
	Y          float64   `json:"y"`
	DX         float64   `json:"dx"`
	DY         float64   `json:"dy"`
	OwnerID    string    `json:"owner_id"`
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
	Target string `json:"target,omitempty"`
	Token  string `json:"token,omitempty"`
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
	jwtSecret   = []byte("Z1OyQ327YsrU42QAu/7lLoHSCelASteNxrv61W/Aa70=") // Необходимо заменить на реальный секретный ключ!
	db          *sql.DB
)

const (
	WIDTH            = 1920
	HEIGHT           = 1080
	MAP_WIDTH        = 10000
	MAP_HEIGHT       = 10000
	PLAYER_SPEED     = 5
	MOB_SPEED        = 2
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
		var targetCID string
		var targetPlayer *Player
		for cid, p := range players {
			if p.Username == targetUsername {
				targetCID = cid
				targetPlayer = p
				break
			}
		}
		if targetPlayer != nil {
			log.Printf("Блокировка игрока %s (%s) - Причина: %s", targetUsername, targetPlayer.IP, reason)
			delete(players, targetCID)
			return map[string]string{"message": fmt.Sprintf("Игрок %s заблокирован.", targetUsername)}
		} else {
			return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}
		}
	case "/kick":
		if len(args) < 1 {
			return map[string]string{"message": "Использование: /kick <имя_пользователя> [причина]"}
		}
		targetUsername := args[0]
		reason := "Кикнут администратором"
		if len(args) > 1 {
			reason = strings.Join(args[1:], " ")
		}
		var targetCID string
		var targetPlayer *Player
		for cid, p := range players {
			if p.Username == targetUsername {
				targetCID = cid
				targetPlayer = p
				break
			}
		}
		if targetPlayer != nil {
			log.Printf("Кик игрока %s (%s) - Причина: %s", targetUsername, targetPlayer.IP, reason)
			delete(players, targetCID)
			return map[string]string{"message": fmt.Sprintf("Игрок %s кикнут.", targetUsername)}
		} else {
			return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}
		}
	case "/list":
		playerList := []string{}
		for pid, p := range players {
			username := p.Username
			if username == "" {
				username = pid[:8]
			}
			playerList = append(playerList, fmt.Sprintf("%s на позиции (%.0f, %.0f)", username, p.X, p.Y))
		}
		if len(playerList) == 0 {
			return map[string]string{"message": "Нет игроков онлайн."}
		}
		return map[string]string{"message": "Игроки онлайн:\n" + strings.Join(playerList, "\n")}

	case "/clear":
		if len(chatHistory) > 0 {
			chatHistory = []ChatMessage{}
			return map[string]string{"message": "История чата очищена."}
		}
		return map[string]string{"message": "История чата уже пуста."}

	case "/restart":
		if len(args) == 0 {
			return map[string]string{"message": "Использование: /restart <секунды>"}
		} else {
			seconds, err := strconv.Atoi(args[0])
			if err != nil {
				return map[string]string{"error": "Неверное количество секунд."}
			}
			log.Printf("Сервер перезапустится через %d секунд...", seconds)
			// TODO: Реализовать логику перезапуска
			return map[string]string{"message": fmt.Sprintf("Сервер перезапустится через %d секунд.", seconds)}
		}
	case "/stop":
		if len(args) == 0 {
			return map[string]string{"message": "Использование: /stop <секунды>"}
		} else {
			seconds, err := strconv.Atoi(args[0])
			if err != nil {
				return map[string]string{"error": "Неверное количество секунд."}
			}
			log.Printf("Сервер остановится через %d секунд...", seconds)
			// TODO: Реализовать логику остановки
			return map[string]string{"message": fmt.Sprintf("Сервер остановится через %d секунд.", seconds)}
		}
	case "/stats":

		uptime := time.Since(startTime).Seconds()
		return map[string]string{"message": fmt.Sprintf("Статистика сервера:\nИгроки онлайн: %d\nВсего клиентов: %d\nВремя работы: %.0f секунд", len(players), len(connections), uptime)}

	case "/level_up":
		if len(args) < 2 {
			return map[string]string{"message": "Использование: /level_up <имя_пользователя> <уровень>"}
		}
		targetUsername := args[0]
		level, err := strconv.Atoi(args[1])
		if err != nil {
			return map[string]string{"error": "Неверный уровень."}
		}
		var targetPlayer *Player
		for _, p := range players {
			if p.Username == targetUsername {
				targetPlayer = p
				break
			}
		}
		if targetPlayer != nil {
			targetPlayer.Level = level
			return map[string]string{"message": fmt.Sprintf("Уровень игрока %s обновлен до %d.", targetUsername, level)}
		} else {
			return map[string]string{"error": fmt.Sprintf("Игрок %s не найден.", targetUsername)}
		}
	case "/help":
		helpText := []string{
			"/ban <имя_пользователя> [причина]",
			"/kick <имя_пользователя> [причина]",
			"/list",
			"/stats",
			"/help",
			"/clear",
			"/restart",
			"/stop",
		}
		return map[string]string{"message": strings.Join(helpText, "\n")}

	default:
		return map[string]string{"error": fmt.Sprintf("Неизвестная команда: %s", cmd)}
	}
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Ошибка обновления:", err)
		return
	}
	defer conn.Close()

	ip := r.RemoteAddr
	isAdmin := false

	cid := uuid.New().String()

	mutex.Lock()
	players[cid] = &Player{
		ID:         cid,
		X:          WIDTH / 2,
		Y:          HEIGHT - 100,
		Direction:  "down",
		Moving:     false,
		Hurt:       false,
		Dead:       false,
		Health:     100,
		IP:         ip,
		IsAdmin:    isAdmin,
		Visible:    true,
		LastUpdate: time.Now(),
		LastAttack: time.Now(),
		LastHurt:   time.Now(),
	}
	connections[cid] = conn
	mutex.Unlock()

	log.Printf("Игрок подключен: %s (%s, админ: %t)", cid, ip, isAdmin)

	// Отправка статуса клиенту
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
				}
			}
		case "input":
			// Перемещение
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

			// Атака
			if msg.Attack {
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

			// Чат
			if msg.Chat != "" {
				message := strings.TrimSpace(msg.Chat)
				if strings.HasPrefix(message, "/") && isAdmin {
					response := handleCommand(cid, message, isAdmin)
					chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: response["message"]})
					if response["error"] != "" {
						chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: response["error"]})
					}
				} else {
					username := player.Username
					if username == "" {
						username = cid[:8]
					}
					chatHistory = append(chatHistory, ChatMessage{Sender: 0, Message: fmt.Sprintf("[%s]: %s", username, message)})
				}
			}
		case "pvp_hit":
			if msg.Target != "" {
				if targetPlayer, exists := players[msg.Target]; exists {
					if time.Since(targetPlayer.LastHurt) > 500*time.Millisecond {
						distance := math.Sqrt(math.Pow(player.X-targetPlayer.X, 2) + math.Pow(player.Y-targetPlayer.Y, 2))
						if distance < 50 {
							targetPlayer.Health -= 20
							targetPlayer.Hurt = true
							targetPlayer.LastHurt = time.Now()
							if targetPlayer.Health <= 0 {
								targetPlayer.Dead = true
								targetPlayer.Health = 0
								go respawnPlayer(targetPlayer)
							}
						}
					}
				}
			}
		}
		mutex.Unlock()
	}

	mutex.Lock()
	delete(players, cid)
	delete(connections, cid)
	mutex.Unlock()
	log.Printf("Игрок отключен: %s", cid)
}

func respawnPlayer(player *Player) {
	time.Sleep(3 * time.Second)
	player.X = WIDTH / 2
	player.Y = HEIGHT - 100
	player.Health = 100
	player.Dead = false
	player.Hurt = false
}

func gameLoop() {
	ticker := time.NewTicker(16 * time.Millisecond) // Примерно 60 FPS
	defer ticker.Stop()

	for range ticker.C {
		mutex.Lock()

		currentTime := time.Now()

		// Обновление позиций моба
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
		}

		// Обновление снарядов
		for id, proj := range projectiles {
			proj.X += proj.DX
			proj.Y += proj.DY
			proj.LastUpdate = currentTime
			if proj.X < 0 || proj.X > MAP_WIDTH || proj.Y < 0 || proj.Y > MAP_HEIGHT {
				delete(projectiles, id)
			}
		}

		// Проверка столкновений снарядов с мобами и игроками
		for projID, proj := range projectiles {
			for mobID, mob := range mobs {
				if math.Abs(proj.X-mob.X) < 32 && math.Abs(proj.Y-mob.Y) < 32 {
					mob.Health -= 10
					delete(projectiles, projID)
					if mob.Health <= 0 {
						delete(mobs, mobID)
						// респаунем нового моба
						spawnRandomMob()
					}
					break
				}
			}

			for playerID, player := range players {
				if proj.OwnerID != playerID {
					if math.Abs(proj.X-player.X) < 32 && math.Abs(proj.Y-player.Y) < 32 {
						player.Health -= 20
						player.Hurt = true
						player.LastHurt = currentTime
						delete(projectiles, projID)
						if player.Health <= 0 {
							player.Dead = true
							player.Health = 0
							go respawnPlayer(player)
						}
						break
					}
				}
			}
		}

		// Готовим игровое состояние
		playersState := make(map[string]interface{})
		for id, p := range players {
			playersState[id] = map[string]interface{}{
				"id":        p.ID,
				"x":         p.X,
				"y":         p.Y,
				"direction": p.Direction,
				"moving":    p.Moving,
				"attacking": p.Attacking,
				"hurt":      p.Hurt,
				"dead":      p.Dead,
				"health":    p.Health,
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
				"id": p.ID,
				"x":  p.X,
				"y":  p.Y,
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

		// Рассылаем всем клиентам
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

func spawnRandomMob() {
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

func registerHandler(w http.ResponseWriter, r *http.Request) {
	log.Printf("Регистрация: запрос от %s", r.RemoteAddr)
	if r.Method != http.MethodPost {
		http.Error(w, "Метод не разрешен", http.StatusMethodNotAllowed)
		return
	}

	var req RegisterRequest
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		log.Printf("Ошибка декодирования JSON: %v", err)
		http.Error(w, "Неверное тело запроса", http.StatusBadRequest)
		return
	}

	if req.Username == "" || req.Password == "" {
		log.Printf("Пустой логин или пароль")
		http.Error(w, "Логин и пароль обязательны", http.StatusBadRequest)
		return
	}

	mutex.Lock()
	defer mutex.Unlock()

	// Проверка, существует ли пользователь в БД
	_, err = getUser(req.Username)
	if err == nil {
		log.Printf("Пользователь %s уже существует", req.Username)
		http.Error(w, "Имя пользователя уже существует", http.StatusConflict)
		return
	} else if err != sql.ErrNoRows {
		log.Printf("Ошибка БД при проверке пользователя: %v", err)
		http.Error(w, "Ошибка сервера", http.StatusInternalServerError)
		return
	}

	// Вставка нового пользователя в БД
	_, err = db.Exec("INSERT INTO users (username, password, is_admin) VALUES ($1, $2, $3)", req.Username, req.Password, false)
	if err != nil {
		log.Printf("Ошибка вставки пользователя: %v", err)
		http.Error(w, "Ошибка сервера", http.StatusInternalServerError)
		return
	}

	log.Printf("Пользователь %s зарегистрирован", req.Username)
	token, err := generateJWT(req.Username)
	if err != nil {
		http.Error(w, "Ошибка генерации токена", http.StatusInternalServerError)
		return
	}

	resp := AuthResponse{
		Success: true,
		Message: "Регистрация успешна!",
		Token:   token,
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func loginHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Метод не разрешен", http.StatusMethodNotAllowed)
		return
	}

	var req LoginRequest
	err := json.NewDecoder(r.Body).Decode(&req)
	if err != nil {
		http.Error(w, "Неверное тело запроса", http.StatusBadRequest)
		return
	}

	mutex.RLock()
	defer mutex.RUnlock()

	user, err := getUser(req.Username)
	if err != nil || user.Password != req.Password {
		http.Error(w, "Неверные учетные данные", http.StatusUnauthorized)
		return
	}

	token, err := generateJWT(user.Username)
	if err != nil {
		http.Error(w, "Ошибка генерации токена", http.StatusInternalServerError)
		return
	}

	resp := AuthResponse{
		Success: true,
		Message: "Вход успешен",
		Token:   token,
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func generateJWT(username string) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"username": username,
		"exp":      time.Now().Add(time.Hour * 24).Unix(),
	})
	return token.SignedString(jwtSecret)
}

func validateJWT(tokenString string) (string, error) {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return jwtSecret, nil
	})
	if err != nil {
		return "", err
	}
	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		if username, ok := claims["username"].(string); ok {
			return username, nil
		}
	}
	return "", fmt.Errorf("invalid token")
}

func loadUsers() {
	usersData.Banned = loadBanned()
	usersData.Admins = loadAdmins()
	usersData.Registered = loadRegistered()

	if len(usersData.Admins) == 0 {
		saveUsers()
		usersData.Admins = loadAdmins()
	}
}

func saveUsers() {
	// Insert default admin if not exists
	_, err := db.Exec("INSERT INTO admins (username) VALUES ('admin') ON CONFLICT (username) DO NOTHING")
	if err != nil {
		log.Println("Ошибка вставки администратора по умолчанию:", err)
	}
}

func getUser(username string) (User, error) {
	var user User
	err := db.QueryRow("SELECT username, password, is_admin FROM users WHERE username = $1", username).Scan(&user.Username, &user.Password, &user.IsAdmin)
	return user, err
}

func loadAdmins() []string {
	rows, err := db.Query("SELECT username FROM admins")
	if err != nil {
		log.Println("Ошибка загрузки администраторов:", err)
		return []string{}
	}
	defer rows.Close()

	var admins []string
	for rows.Next() {
		var username string
		err := rows.Scan(&username)
		if err != nil {
			log.Println("Ошибка сканирования администратора:", err)
			continue
		}
		admins = append(admins, username)
	}
	return admins
}

func loadBanned() []string {
	rows, err := db.Query("SELECT username FROM banned")
	if err != nil {
		log.Println("Ошибка загрузки заблокированных:", err)
		return []string{}
	}
	defer rows.Close()

	var banned []string
	for rows.Next() {
		var username string
		err := rows.Scan(&username)
		if err != nil {
			log.Println("Ошибка сканирования заблокированного:", err)
			continue
		}
		banned = append(banned, username)
	}
	return banned
}

func loadRegistered() []User {
	rows, err := db.Query("SELECT username, password, is_admin FROM users")
	if err != nil {
		log.Println("Ошибка загрузки пользователей:", err)
		return []User{}
	}
	defer rows.Close()

	var users []User
	for rows.Next() {
		var user User
		err := rows.Scan(&user.Username, &user.Password, &user.IsAdmin)
		if err != nil {
			log.Println("Ошибка сканирования пользователя:", err)
			continue
		}
		users = append(users, user)
	}
	return users
}

func createTables() {
	// Создание таблицы пользователей
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS users (
			id SERIAL PRIMARY KEY,
			username VARCHAR(50) UNIQUE NOT NULL,
			password VARCHAR(255) NOT NULL,
			is_admin BOOLEAN DEFAULT FALSE
		)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы users:", err)
	}

	// Создание таблицы администраторов
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS admins (
			id SERIAL PRIMARY KEY,
			username VARCHAR(50) UNIQUE NOT NULL
		)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы admins:", err)
	}

	// Создание таблицы заблокированных пользователей
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS banned (
			id SERIAL PRIMARY KEY,
			username VARCHAR(50) UNIQUE NOT NULL
		)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы banned:", err)
	}

	// Создание таблицы игроков (для сохранения прогресса)
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS players (
			id VARCHAR(36) PRIMARY KEY,
			username VARCHAR(50),
			x REAL DEFAULT 960,
			y REAL DEFAULT 980,
			direction VARCHAR(10) DEFAULT 'down',
			health INTEGER DEFAULT 100,
			level INTEGER DEFAULT 1,
			ip VARCHAR(45),
			is_admin BOOLEAN DEFAULT FALSE,
			visible BOOLEAN DEFAULT TRUE,
			last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		log.Fatal("Ошибка создания таблицы players:", err)
	}

	log.Println("Таблицы созданы успешно")
}

func main() {
	rand.Seed(time.Now().UnixNano())

	// Подключение к PostgreSQL
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		log.Fatal("DATABASE_URL не установлена")
	}
	var err error
	db, err = sql.Open("postgres", databaseURL)
	if err != nil {
		log.Fatal("Ошибка подключения к БД:", err)
	}
	defer db.Close()

	// Создание таблиц
	createTables()

	loadUsers()
	initMobs()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/ws", wsHandler)
	http.HandleFunc("/register", registerHandler)
	http.HandleFunc("/login", loginHandler)

	go gameLoop()

	log.Printf("Запуск сервера на порту %s...", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
