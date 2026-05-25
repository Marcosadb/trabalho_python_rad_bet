from flask import Flask, render_template, request, redirect, flash, session, jsonify, url_for
import sqlite3
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__, template_folder='TEMPLETES')
app.secret_key = 'chave_secreta_wyden_bet' 

def conectar_banco():
    conn = sqlite3.connect('wyden_bet.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apostas'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(apostas)")
        colunas = [linha['name'] for linha in cursor.fetchall()]
        if 'bilhete_id' not in colunas:
            cursor.execute("ALTER TABLE apostas ADD COLUMN bilhete_id TEXT NOT NULL DEFAULT ''")
        if 'esporte' not in colunas:
            cursor.execute("ALTER TABLE apostas ADD COLUMN esporte TEXT NOT NULL DEFAULT ''")
        if 'data_horario' not in colunas:
            cursor.execute("ALTER TABLE apostas ADD COLUMN data_horario TEXT DEFAULT ''")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            matricula TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            saldo REAL DEFAULT 30.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            bilhete_id TEXT NOT NULL,
            esporte TEXT NOT NULL,
            jogo_titulo TEXT NOT NULL,
            opcao_selecionada TEXT NOT NULL,
            odd REAL NOT NULL,
            valor REAL NOT NULL,
            status TEXT DEFAULT 'Pendente',
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='partidas'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(partidas)")
        cols = [r['name'] for r in cursor.fetchall()]
        if 'data_horario' not in cols:
            cursor.execute("ALTER TABLE partidas ADD COLUMN data_horario TEXT DEFAULT ''")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS partidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_casa TEXT NOT NULL,
            time_visitante TEXT NOT NULL,
            esporte TEXT NOT NULL,
            data_horario TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    return conn

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        matricula = request.form.get('matricula')
        email = request.form.get('email')
        senha = request.form.get('senha')
        conn = conectar_banco()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO usuarios (nome, matricula, email, senha, saldo) VALUES (?, ?, ?, ?, ?)', 
                           (nome, matricula, email, senha, 30.0))
            conn.commit()
            flash("Cadastro realizado com sucesso! Faça login.")
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash("Matrícula ou E-mail já cadastrados!")
            return redirect('/cadastro')
        finally:
            conn.close()
    return render_template('cadastro.html')

@app.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        flash("Instruções de recuperação enviadas para o seu e-mail!")
        return redirect('/login')
    return render_template('recuperar.html')

@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_input = request.form.get('usuario')
        senha_input = request.form.get('senha')
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM usuarios WHERE matricula = ? OR email = ?', (usuario_input, usuario_input))
        usuario = cursor.fetchone()
        conn.close()
        if usuario and usuario['senha'] == senha_input:
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            return redirect('/dashboard')
        else:
            flash("Matrícula/E-mail ou Senha incorretos!")
            return redirect('/login')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT nome, saldo FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = cursor.fetchone()
    def buscar_um_jogo(esporte):
        c = conectar_banco()
        cur = c.cursor()
        try:
            cur.execute('SELECT * FROM partidas WHERE esporte = ? LIMIT 1', (esporte.lower(),))
            p = cur.fetchone()
            if p:
                return {'titulo': f"{p['time_casa']} vs {p['time_visitante']}", 'opcao1': p['time_casa'], 'opcao2': p['time_visitante'], 'modalidade': esporte}
            return None
        finally:
            c.close()

    cursor.execute('SELECT * FROM apostas WHERE usuario_id = ? ORDER BY id DESC', (session['usuario_id'],))
    historico_db = cursor.fetchall()
    
    bilhetes = {}
    for h in historico_db:
        try:
            b_id = h['bilhete_id'] if h['bilhete_id'] else 'sem-id'
        except (IndexError, KeyError):
            b_id = 'sem-id'

        row = dict(h)
        try:
            raw_dt = row.get('data_horario') or ''
            if raw_dt:
                try:
                    parsed = datetime.fromisoformat(raw_dt)
                except Exception:
                    parsed = None
                if parsed:
                    row['data_horario_display'] = parsed.strftime('%d/%m/%Y %H:%M')
                else:
                    row['data_horario_display'] = raw_dt
            else:
                row['data_horario_display'] = ''
        except Exception:
            row['data_horario_display'] = ''
        if b_id not in bilhetes:
            bilhetes[b_id] = {
                'apostas': [],
                'valor_total': float(row.get('valor') or 0.0),
                'odd_total': 1.0,
                'esportes': [],
            }

        bilhetes[b_id]['apostas'].append(row)
        esporte_val = row.get('esporte') or ''
        if esporte_val and esporte_val not in bilhetes[b_id]['esportes']:
            bilhetes[b_id]['esportes'].append(esporte_val)
        try:
            bilhetes[b_id]['odd_total'] *= float(row.get('odd') or 1.0)
        except (TypeError, ValueError):
            bilhetes[b_id]['odd_total'] *= 1.0

    for bilhete in bilhetes.values():
        bilhete['retorno_total'] = bilhete['valor_total'] * bilhete['odd_total']

    jogo_futebol = buscar_um_jogo('Futebol')
    jogo_volei = buscar_um_jogo('Volei')
    jogo_basquete = buscar_um_jogo('Basquete')

    principais_jogos = []
    if jogo_futebol:
        principais_jogos.append({
            'modalidade': 'futebol',
            'titulo': jogo_futebol['titulo'],
            'link': '/esportes/futebol'
        })
    if jogo_volei:
        principais_jogos.append({
            'modalidade': 'volei',
            'titulo': jogo_volei['titulo'],
            'link': '/esportes/volei'
        })
    if jogo_basquete:
        principais_jogos.append({
            'modalidade': 'basquete',
            'titulo': jogo_basquete['titulo'],
            'link': '/esportes/basquete'
        })

    conn.close()
    return render_template('dashboard.html', 
                           nome=usuario['nome'], 
                           saldo=usuario['saldo'], 
                           bilhetes=bilhetes,
                           historico_apostas=historico_db,
                           principais_jogos=principais_jogos)

@app.route('/carteira')
def carteira():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT nome, saldo FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = cursor.fetchone()
    conn.close()
    return render_template('carteira.html', nome=usuario['nome'], saldo=usuario['saldo'])

@app.route('/solicitar-saque', methods=['POST'])
def solicitar_saque():
    if 'usuario_id' not in session: return redirect(url_for('login'))
    try:
        valor_saque = float(request.form.get('valor', 0))
    except ValueError:
        flash("Valor inválido!", "error")
        return redirect(url_for('dashboard'))
    
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT saldo FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = cursor.fetchone()
    
    if usuario and usuario['saldo'] >= valor_saque and valor_saque > 0:
        cursor.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (valor_saque, session['usuario_id']))
        conn.commit()
        flash('Saque realizado com sucesso!', 'success')
    else:
        flash('Saldo insuficiente ou valor inválido!', 'error')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/processar-aposta', methods=['POST'])
def processar_aposta():
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autenticado"}), 403
    dados = request.json
    valor_total = float(dados.get('valor', 0))
    jogos = dados.get('jogos', [])
    bilhete_id = str(uuid.uuid4())[:8]
    
    conn = conectar_banco()
    cur = conn.cursor()
    cur.execute('SELECT saldo FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = cur.fetchone()
    
    if usuario and usuario['saldo'] >= valor_total:
        cur.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (valor_total, session['usuario_id']))
        for item in jogos:
            data_horario = ''
            try:
                cur.execute("SELECT data_horario FROM partidas WHERE esporte = ? AND (time_casa || ' vs ' || time_visitante) = ?", (item.get('esporte', ''), item['jogo']))
                partida = cur.fetchone()
                if partida:
                    data_horario = partida['data_horario']
            except Exception:
                data_horario = ''
            cur.execute('''INSERT INTO apostas (usuario_id, bilhete_id, esporte, jogo_titulo, opcao_selecionada, odd, valor, data_horario, status) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                        (session['usuario_id'], bilhete_id, item.get('esporte', ''), item['jogo'], item['opcao'], float(item['odd']), valor_total, data_horario, 'Pendente'))
        conn.commit()
        conn.close()
        
        flash('Aposta criada.', 'success')
        return jsonify({"status": "sucesso", "mensagem": "Aposta criada.", "redirect": url_for('dashboard')})
    
    conn.close()
    return jsonify({"status": "erro", "mensagem": "Saldo insuficiente!"}), 400

@app.route('/esportes/<modalidade>')
def esportes(modalidade):
    if 'usuario_id' not in session: return redirect('/login')
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT nome, saldo FROM usuarios WHERE id = ?', (session['usuario_id'],))
    usuario = cursor.fetchone()
    cursor.execute('SELECT * FROM partidas WHERE esporte = ? ORDER BY data_horario ASC', (modalidade.lower(),))
    partidas = cursor.fetchall()
    conn.close()
    jogos_dinamicos = []
    for p in partidas:
        data_h = p['data_horario'] if 'data_horario' in p.keys() and p['data_horario'] else ''
        display_dt = ''
        if data_h:
            try:
                parsed = datetime.fromisoformat(data_h)
                display_dt = parsed.strftime('%d/%m/%Y %H:%M')
            except Exception:
                display_dt = data_h
        jogos_dinamicos.append({'titulo': f"{p['time_casa']} vs {p['time_visitante']}", 'opcao1': p['time_casa'], 'odd1': float(round(random.uniform(1.5, 3.5), 2)), 'opcao2': p['time_visitante'], 'odd2': float(round(random.uniform(1.5, 3.5), 2)), 'data_horario': data_h, 'data_horario_display': display_dt})
    return render_template('esporte.html', modalidade=modalidade.capitalize(), saldo=usuario['saldo'], jogos=jogos_dinamicos)

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('login'))

def inicializar_partidas():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM partidas")
    if cursor.fetchone()[0] == 0:
        times_por_esporte = {
            'volei': ['Eng. Civil', 'Ed. Física', 'Direito', 'Psicologia'],
            'basquete': ['ADS', 'Eng. Mecânica', 'Contábeis', 'Adm'],
            'futebol': ['Adm', 'Direito', 'Ed. Física', 'ADS']
        }
        def gerar_calendario(esporte, equipes, num_jogos=8):
            try:
                tz = ZoneInfo('America/Sao_Paulo')
            except Exception:
                from datetime import timezone
                tz = timezone(timedelta(hours=-3))
            hoje = datetime.now(tz).date()
            dias_ate_prox_sab = (5 - hoje.weekday()) % 7
            if dias_ate_prox_sab == 0: dias_ate_prox_sab = 7
            data_inicio = hoje + timedelta(days=dias_ate_prox_sab)
            jogos = []
            jogos_criados = 0
            current_week_start = data_inicio
            horarios = [(0, 10, 0), (1, 10, 30)]
            while jogos_criados < num_jogos:
                for day_off, hour, minute in horarios:
                    if jogos_criados >= num_jogos: break
                    game_date = current_week_start + timedelta(days=day_off)
                    t1, t2 = random.sample(equipes, 2) if len(equipes) >= 2 else (equipes[0], equipes[0])
                    dt = datetime(game_date.year, game_date.month, game_date.day, hour, minute, tzinfo=tz)
                    jogos.append((t1, t2, dt.isoformat()))
                    jogos_criados += 1
                current_week_start = current_week_start + timedelta(days=7)
            return jogos
        for esporte, equipes in times_por_esporte.items():
            for casa, visitante, dt_iso in gerar_calendario(esporte, equipes, num_jogos=8):
                cursor.execute('INSERT INTO partidas (time_casa, time_visitante, esporte, data_horario) VALUES (?, ?, ?, ?)', (casa, visitante, esporte, dt_iso))
        conn.commit()
    conn.close()

if __name__ == '__main__':
    inicializar_partidas() 
    app.run(debug=True)