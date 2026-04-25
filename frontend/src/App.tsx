import { useEffect, useMemo, useState } from 'react';
import InboundCallsPage from './pages/InboundCallsPage';
import { apiService } from './services/api';

type ActiveSection = 'dashboard' | 'inbound';

function App() {
  const [activeSection, setActiveSection] = useState<ActiveSection>('dashboard');
  const [isConnected, setIsConnected] = useState(false);
  const [clientName, setClientName] = useState('TeleCorp');
  const [customerCount, setCustomerCount] = useState(0);

  useEffect(() => {
    const refreshOverview = async () => {
      try {
        const [health, customers] = await Promise.all([
          apiService.checkHealth(),
          apiService.getCustomers(),
        ]);
        setIsConnected(health.ollama === 'connected');
        setCustomerCount(customers.length);
        if (health.client_name) {
          setClientName(health.client_name);
        }
      } catch {
        setIsConnected(false);
      }
    };

    refreshOverview();
    const interval = setInterval(refreshOverview, 10000);
    return () => clearInterval(interval);
  }, []);

  const statusText = useMemo(() => {
    return isConnected ? 'Ollama Connected' : 'Ollama Disconnected';
  }, [isConnected]);

  return (
    <div className="workspace-shell">
      <header className="workspace-topbar">
        <div>
          <p className="workspace-kicker">MIC Operations</p>
          <h1>Call Center Control Desk</h1>
        </div>
        <div className={`workspace-status ${isConnected ? 'ok' : 'bad'}`}>{statusText}</div>
      </header>

      <nav className="workspace-nav">
        <button
          className={`workspace-nav-button ${activeSection === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveSection('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`workspace-nav-button ${activeSection === 'inbound' ? 'active' : ''}`}
          onClick={() => setActiveSection('inbound')}
        >
          Inbound Call Center
        </button>
      </nav>

      {activeSection === 'dashboard' && (
        <section className="clean-dashboard">
          <div className="clean-hero">
            <h2>Single-screen operations, zero clutter.</h2>
            <p>
              Login and extra modules were removed. This workspace now keeps only the Dashboard and
              Inbound Call Center flow.
            </p>
            <button className="clean-cta" onClick={() => setActiveSection('inbound')}>
              Open Inbound Call Center
            </button>
          </div>

          <div className="clean-metrics">
            <article className="clean-metric-card">
              <h3>Ollama</h3>
              <p className={isConnected ? 'metric-ok' : 'metric-bad'}>{statusText}</p>
            </article>
            <article className="clean-metric-card">
              <h3>Client</h3>
              <p>{clientName}</p>
            </article>
            <article className="clean-metric-card">
              <h3>Customers</h3>
              <p>{customerCount}</p>
            </article>
          </div>
        </section>
      )}

      {activeSection === 'inbound' && <InboundCallsPage />}
    </div>
  );
}

export default App;
