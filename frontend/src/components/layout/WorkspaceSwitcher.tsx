import { ChevronDown, Layers3 } from "lucide-react";

export function WorkspaceSwitcher() {
  return (
    <button className="workspace-switcher" type="button" aria-label="切换工作空间">
      <span className="workspace-switcher-icon"><Layers3 size={15} aria-hidden="true" /></span>
      <span className="workspace-switcher-copy">
        <small>当前工作空间</small>
        <strong>ProductAlert</strong>
      </span>
      <ChevronDown size={15} aria-hidden="true" />
    </button>
  );
}
