from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocket
from parser import parse_category
from sqlmodel import Field, SQLModel, create_engine, Session, select
from typing import List

app = FastAPI()
sqlite_url = "sqlite:///parser.db"
engine = create_engine(sqlite_url)


class Prices(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str
    cost: int


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Depends(get_session)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                self.disconnect(connection)


manager = ConnectionManager()


async def background_parser(session: Session):
    parsed_items = parse_category()
    notifications = []

    for item in parsed_items:
        existing = session.exec(select(Prices).where(Prices.id == item["id"])).first()
        if existing:
            existing.name = item["name"]
            existing.cost = item["price"]
            notifications.append(f"Updated: {existing.name} with price {existing.cost}")
        else:
            new_item = Prices(id=item["id"], name=item["name"], cost=item["price"])
            session.add(new_item)
            notifications.append(f"Added: {new_item.name} with price {new_item.cost}")

    session.commit()

    for notification in notifications:
        await manager.broadcast(notification)


@app.on_event("startup")
async def startup_event():
    create_db_and_tables()


@app.post("/start_parser/")
async def start_parser(background_tasks: BackgroundTasks, session: Session = SessionDep):
    background_tasks.add_task(background_parser, session)
    return {"message": "Парсер запущен в фоне."}


@app.get("/prices/", response_model=List[Prices])
async def read_prices(session: Session = SessionDep, offset: int = 0, limit: int = 100):
    return session.exec(select(Prices).offset(offset).limit(limit)).all()


@app.get("/prices/{item_id}", response_model=Prices)
async def read_item(item_id: int, session: Session = SessionDep):
    price = session.get(Prices, item_id)
    if not price:
        raise HTTPException(status_code=404, detail="Price not found")
    return price


@app.put("/prices/{item_id}", response_model=Prices)
async def update_item(item_id: int, data: Prices, session: Session = SessionDep):
    price_db = session.get(Prices, item_id)
    if not price_db:
        raise HTTPException(status_code=404, detail="Price not found")
    price_db.name = data.name
    price_db.cost = data.cost
    session.add(price_db)
    session.commit()
    session.refresh(price_db)

    await manager.broadcast(f"Updated: {price_db.name} with price {price_db.cost}")
    return price_db


@app.post("/prices/create", response_model=Prices)
async def create_item(item: Prices, session: Session = SessionDep):
    session.add(item)
    session.commit()
    session.refresh(item)

    await manager.broadcast(f"Added: {item.name} with price {item.cost}")
    return item


@app.delete("/prices/{item_id}")
async def delete_item(item_id: int, session: Session = SessionDep):
    price = session.get(Prices, item_id)
    if not price:
        raise HTTPException(status_code=404, detail="Price not found")
    session.delete(price)
    session.commit()

    await manager.broadcast(f"Deleted: Item with ID {item_id}")
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
