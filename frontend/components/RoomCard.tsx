"use client";

import { createRoom } from "../lib/api/rooms";

export default function RoomCard() {

    async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {

        e.preventDefault();

        const formData = new FormData(e.currentTarget);
        const title = formData.get("RoomTitle") as string;

        await createRoom({ title });
    }

    return (

        <div className="border border-gray-300 rounded p-4 mb-4">
            <form onSubmit={handleSubmit}>
                <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="RoomTitle">
                    Room Title
                </label>
                <input type="text" id="RoomTitle" name="RoomTitle" className="border border-gray-300 rounded px-2 py-1 w-full" placeholder="Enter Room title" />
                <button type="submit" className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mt-2">
                    Create Room
                </button>
            </form>
        </div>
    );
}
