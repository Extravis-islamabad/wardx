import { RouterProvider } from 'react-router-dom';
import RootProvider from './provider';
import routes from './router';

const App = () => (
  <RootProvider>
    <RouterProvider router={routes} />
  </RootProvider>
);

export default App;
