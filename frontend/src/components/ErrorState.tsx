export default function ErrorState({
  title = "오류",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <div className="rounded-lg border border-red-800 bg-red-950/30 p-6">
      <h3 className="mb-2 font-semibold text-red-400">{title}</h3>
      <p className="text-sm text-red-300">{message}</p>
    </div>
  );
}
