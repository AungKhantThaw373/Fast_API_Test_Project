const API_URL = "http://localhost:8000";

export type Post = {
    id?: number;
    title: string;
    created_at?: string;
    updated_at?: string;
};

export async function getRooms(): Promise<Post[]> {
    const res = await fetch(`${API_URL}/rooms`);
    return res.json();
}

export async function createRoom(data: Omit<Post, "id">) {
    return fetch(`${API_URL}/rooms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }).then(() => {
        alert("Room created successfully with title: " + data.title);
    });
}