import joblib

model = joblib.load('app/ml/xgb_classification_tuned.joblib')
print('Model object:', model)
print('\nModel type:', type(model))
print('Has feature_names_in_?', hasattr(model, 'feature_names_in_'))
print('Has n_features_in_?', hasattr(model, 'n_features_in_'))

if hasattr(model, 'n_features_in_'):
    print('\nNumber of features:', model.n_features_in_)
    
if hasattr(model, 'feature_names_in_'):
    print('\nFeature names:')
    for i, name in enumerate(model.feature_names_in_, 1):
        print(f"  {i}. {name}")
