import RoomCard from "../components/RoomCard";

export default function Home() {
  return (
    <div>
      <h1 className="text-4xl font-bold text-center mt-10">Welcome to the AI Chat App</h1>
      <div className="max-w-2xl mx-auto mt-11">
        <RoomCard />
      </div>
    </div>
  );
}

