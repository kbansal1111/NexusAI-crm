import { TaskList } from "@/features/tasks/components/task-list";

export const dynamic = "force-dynamic";

export default function BDTasksPage() {
    return (
        <div className="pt-4">
            <TaskList />
        </div>
    );
}
