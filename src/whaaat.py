#PARA BORRAR TODO

"""from database import DB
db = DB()

# Borrar el documento y sus entitats (si en té)
db.conn.execute("DELETE FROM entities WHERE doc_id=1")
db.conn.execute("DELETE FROM hypotheses")
db.conn.execute("DELETE FROM documents WHERE id=1")
db.conn.commit()
db.summary()
db.close()"""


#PARA BORRAR LAS GEOCODIFICACIONES
"""
from database import DB
db = DB()
db.conn.execute("UPDATE entities SET lat=NULL, lon=NULL, geo_status=NULL, geo_name=NULL")
db.conn.commit()
print("Geocodificació resetejada")
db.close()"""

#PARA BORRAR UN DOCUMENTO Y SUS ENTIDADES DE LA BASE DE DATOS

from database import DB
db = DB()
doc = db.conn.execute("SELECT id FROM documents WHERE title='carvajal_1542_cronica'").fetchone()
if doc:
    db.conn.execute("DELETE FROM hypotheses WHERE entity_id IN (SELECT id FROM entities WHERE doc_id=?)", (doc["id"],))
    db.conn.execute("DELETE FROM entities WHERE doc_id=?", (doc["id"],))
    db.conn.execute("DELETE FROM documents WHERE id=?", (doc["id"],))
    db.conn.commit()
    print("Esborrat carvajal_1542_cronica")
db.summary()
db.close()