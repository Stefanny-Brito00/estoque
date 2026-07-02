import os
import cv2
import sqlite3

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime


app = Flask(__name__)
app.secret_key = "segredo_estoque_pro"
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def get_db():
    conn = sqlite3.connect('estoque.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- INICIALIZAÇÃO DO BANCO (COM NOVAS COLUNAS) ---
def init_db():
    conn = get_db()
    # Adicionamos 'categoria' e 'min_estoque'
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            codigo TEXT,
            categoria TEXT,
            preco REAL,
            qtd INTEGER,
            min_estoque INTEGER DEFAULT 5,
            validade TEXT,
            imagem TEXT
        )
    ''')
    conn.commit()
    conn.close()

## --- ROTA INICIAL (Protegida) ---
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('app.html')

# --- ROTA DE LOGIN (Inteligente) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        usuario = request.form['user']
        senha = request.form['pass']
        
        # .lower() transforma tudo em minúsculo antes de conferir
        # Assim: 'Admin', 'ADMIN', 'admin' -> todos viram 'admin'
        if usuario.lower() == 'admin' and senha.lower() == 'admin':
            session['user'] = 'admin'
            return redirect(url_for('index'))
        else:
            erro = "Login incorreto"
            
    return render_template('login.html', erro=erro)

# --- ROTA DE SAIR ---
@app.route('/logout')
def logout():
    session.pop('user', None) # Remove o usuário da memória
    return redirect(url_for('login'))

# --- API: LISTAR (COM LÓGICA FIFO E ALERTAS) ---
@app.route('/api/listar')
def listar():
    conn = get_db()
    # ORDER BY validade ASC -> Implementa o conceito FIFO (Mostra o que vence antes primeiro)
    produtos = conn.execute("SELECT * FROM produtos ORDER BY validade ASC").fetchall()
    conn.close()
    
    lista = []
    hoje = datetime.now()
    
    for p in produtos:
        try:
            val_dt = datetime.strptime(p['validade'], '%Y-%m-%d')
            dias_vencimento = (val_dt - hoje).days
        except:
            dias_vencimento = 999

        # Status de Validade
        if dias_vencimento < 0: status_val = 'vencido'
        elif dias_vencimento < 7: status_val = 'perigo' # Vence em 1 semana
        elif dias_vencimento < 30: status_val = 'atencao'
        else: status_val = 'ok'

        # Alerta de Estoque Baixo
        alerta_estoque = True if p['qtd'] <= p['min_estoque'] else False

        lista.append({
            "id": p['id'],
            "nome": p['nome'],
            "codigo": p['codigo'],
            "categoria": p['categoria'],
            "preco": p['preco'],
            "qtd": p['qtd'],
            "min_estoque": p['min_estoque'],
            "validade": p['validade'],
            "imagem": p['imagem'],
            "status_val": status_val,
            "alerta_estoque": alerta_estoque,
            "dias_vencimento": dias_vencimento
        })
    
    return jsonify(lista)

# --- API: ADICIONAR OU EDITAR ---
@app.route('/api/salvar', methods=['POST'])
def salvar():
    data = request.form
    file = request.files.get('foto')
    
    conn = get_db()
    
    # Se tem ID, é EDIÇÃO
    if 'id' in data and data['id']:
        # Lógica para manter a imagem antiga se não enviou nova
        img_sql = ""
        params = [data['nome'], data['codigo'], data['categoria'], data['preco'], data['qtd'], data['min_estoque'], data['validade']]
        
        if file:
            filename = secure_filename(f"{data['codigo']}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            img_sql = ", imagem = ?"
            params.append(filename)
            
        params.append(data['id']) # ID vai no final pro WHERE
        
        conn.execute(f'''UPDATE produtos SET 
                        nome=?, codigo=?, categoria=?, preco=?, qtd=?, min_estoque=?, validade=? {img_sql}
                        WHERE id=?''', params)
    
    # Se não tem ID, é NOVO
    else:
        filename = ""
        if file:
            filename = secure_filename(f"{data['codigo']}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        conn.execute('''INSERT INTO produtos 
                        (nome, codigo, categoria, preco, qtd, min_estoque, validade, imagem) 
                        VALUES (?,?,?,?,?,?,?,?)''',
                     (data['nome'], data['codigo'], data['categoria'], data['preco'], data['qtd'], data['min_estoque'], data['validade'], filename))
    
    conn.commit()
    conn.close()
    return jsonify({"msg": "Salvo com sucesso"})

# --- API: EXCLUIR ---
@app.route('/api/excluir/<int:id_prod>', methods=['DELETE'])
def excluir(id_prod):
    conn = get_db()
    conn.execute("DELETE FROM produtos WHERE id=?", (id_prod,))
    conn.commit()
    conn.close()
    return jsonify({"msg": "Deletado"})

# --- API: BUSCAR POR CÓDIGO ---
@app.route('/api/buscar/<codigo>')
def buscar_codigo(codigo):
    conn = get_db()
    prod = conn.execute("SELECT * FROM produtos WHERE codigo = ?", (codigo,)).fetchone()
    conn.close()
    if prod:
        return jsonify(dict(prod))
    return jsonify(None)

# --- ROTA PARA MOSTRAR AS IMAGENS (Correção do Erro 404) ---
@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)