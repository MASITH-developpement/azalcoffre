import React from 'react';
import { Link } from 'react-router-dom';

export default function NotFoundPage(): React.ReactElement {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gray-50">
      <div className="text-center">
        <div className="text-6xl font-bold text-gray-200 mb-4">404</div>
        <h1 className="text-xl font-semibold text-gray-900 mb-2">Page non trouvee</h1>
        <p className="text-gray-500 mb-6">
          La page que vous recherchez n'existe pas ou a ete deplacee.
        </p>
        <Link
          to="/"
          className="btn btn-primary"
        >
          Retour a l'accueil
        </Link>
      </div>
    </div>
  );
}
