import { Route, Routes } from "react-router-dom";
import { Shell } from "./layout/Shell";
import { DashboardPage } from "./pages/DashboardPage";
import { OperationsPage } from "./pages/OperationsPage";
import { MapPage } from "./pages/MapPage";
import { LandingPage } from "./pages/LandingPage";
import { PrivacyPolicyPage } from "./pages/PrivacyPolicyPage";
import { ConfirmedPage } from "./pages/ConfirmedPage";

const App = () => (
  <Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/landing" element={<LandingPage />} />
    <Route path="/confirmed" element={<ConfirmedPage />} />
    <Route path="/datenschutz" element={<PrivacyPolicyPage />} />
    <Route path="/app" element={<Shell />}>
      <Route index element={<DashboardPage />} />
      <Route path="operations" element={<OperationsPage />} />
      <Route path="map" element={<MapPage />} />
    </Route>
  </Routes>
);

export default App;
