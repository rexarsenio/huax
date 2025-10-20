import { Route, Routes } from "react-router-dom";
import { Shell } from "./layout/Shell";
import { DashboardPage } from "./pages/DashboardPage";
import { OperationsPage } from "./pages/OperationsPage";
import { MapPage } from "./pages/MapPage";

const App = () => (
  <Routes>
    <Route path="/" element={<Shell />}>
      <Route index element={<DashboardPage />} />
      <Route path="operations" element={<OperationsPage />} />
      <Route path="map" element={<MapPage />} />
    </Route>
  </Routes>
);

export default App;
