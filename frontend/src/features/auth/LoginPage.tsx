import { FormEvent, useState } from "react";
import { ArrowLeft, LockKeyhole, LogIn, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { login, register } from "../../api/auth";

type AuthMode = "login" | "register";

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body) as { detail?: string };
      return parsed.detail || error.message;
    } catch {
      return error.body || error.message;
    }
  }
  return "请求失败，请确认 API 服务是否已启动。";
}

export function LoginPage() {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("operator@productalert.cn");
  const [password, setPassword] = useState("productalert-demo");
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");
  const [message, setMessage] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("loading");
    setMessage("");
    try {
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({ email, password });
      }
      setStatus("success");
      setMessage("认证成功，可以返回工作台读取真实 API 数据。");
    } catch (error) {
      setStatus("idle");
      setMessage(errorMessage(error));
    }
  };

  return (
    <main className="auth-page">
      <section className="panel auth-panel">
        <Link className="back-link" to="/overview"><ArrowLeft size={15} /> 返回工作台</Link>
        <div className="auth-icon"><LockKeyhole size={22} /></div>
        <div className="eyebrow">PRODUCTALERT API ACCESS</div>
        <h1>{mode === "login" ? "登录 ProductAlert" : "注册新账号"}</h1>
        <p>登录后，监控中心、情报收件箱和变化详情会优先读取后端真实 API；未登录时继续显示演示数据。</p>

        <div className="auth-mode-switch" role="tablist" aria-label="认证模式">
          <button className={mode === "login" ? "is-active" : ""} type="button" onClick={() => { setMode("login"); setMessage(""); }}>
            <LogIn size={15} /> 登录 ProductAlert
          </button>
          <button className={mode === "register" ? "is-active" : ""} type="button" onClick={() => { setMode("register"); setMessage(""); }}>
            <UserPlus size={15} /> 注册新账号
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label className="field-label" htmlFor="auth-email">邮箱</label>
          <input id="auth-email" className="url-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <label className="field-label" htmlFor="auth-password">密码</label>
          <input id="auth-password" className="url-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
          <button className="primary-button auth-submit" type="submit" disabled={status === "loading"}>
            {status === "loading" ? "正在连接 API…" : "进入工作台"}
          </button>
        </form>

        {message ? <div className={`auth-message ${status === "success" ? "success" : "error"}`} role="status">{message}</div> : null}
        {status === "success" ? <Link className="button button-secondary auth-return" to="/overview">进入工作台</Link> : null}
      </section>
    </main>
  );
}
