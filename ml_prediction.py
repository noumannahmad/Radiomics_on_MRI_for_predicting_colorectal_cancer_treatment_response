import pandas as pd
import numpy as np
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn import metrics
import csv
import os.path


def create_evaluate_model(method, params, selectedFeatures, selectionFeaturesPath, manualFeaturesPath, paramSearchResultsPath, optimizeParams, scoringOptiMetric = 'r2'):
    """
    ACTION: 
        Train a specified model on the training data. The model parameters will be optimized by cross-validation if specified. 
        The train/test-division of the data is hard coded by patient indices in this function. 
        The model is evaluated by cross-validation on the training data and tested on the test data. 
    INPUTS: 
        method: machine learning algorithm to use, eg. 'RFreg' (random forest regression), 'RFclass' (random forest classifier), 'LogReg' (logistic regression)
        params: parameter settings for the selected method (a dictionary, values can be lists)
                For RFreg: n_estimators, max_features, max_depth
                For RFclass: n_estimators, max_features, max_depth
                For LogReg: penalty, solver, C, max_iter
        selectedFeatures: list of features to use when traning a model
        selectionFeaturesPath: path to selectionFeatures file
        manualFeaturesPath: path to manualFeatures file
        paramSearchResultsPath: path to csv-file that will be created, containing results from the parameter optimization
        optimizeParams: boolean, if True, GridSearchCV is used to find the best parameter setting
        scoringOptiMetric: metric to optimize, over the given set of parameters
    OUTPUTS: 
        yTrueTest: Numpy-array with true outcome values of the test data
        yPredRegTest: Numpy-array with predicted regression outcome values of the test data (integers for classification methods)
        yTrueVal: Numpy-array with true outcome values of the validation data
        yPredRegVal: Numpy-array with predicted regression outcome values of the validation data (integers for classification methods)
        params: The parameter settings that was used on the validation and test data
    """

    # Read input data from csv-files
    X = pd.read_csv(selectionFeaturesPath, index_col=0, delimiter=';') # All data in selectionFeatures.csv
    X = X[selectedFeatures] # Filter on the selected features
    idX = X.index.values # Patients with input data

    # Read output data from csv-files
    y = pd.read_csv(manualFeaturesPath, index_col=0, delimiter=';') # All data in manualFeatures.csv
    y = y[y['outcome'] >= 0] # Keep only patients with given outcome
    y = y[['outcome']] # Keep only outcome
    idY = y.index.values # Patients with output data

    # Select patiets that have both input and output
    patIds = np.array([id for id in idX if id in idY])
    X = X.loc[patIds]
    y = y.loc[patIds]

    # Divide data into train- and test-data
    testIds = [1, 8, 13, 20, 40, 44, 49, 55]
    trainIds = [v for v in X.index.values if v not in testIds]

    yTest = y.loc[testIds]
    Xtest = X.loc[testIds]
    yTrain = y.loc[trainIds]
    Xtrain = X.loc[trainIds]

    if optimizeParams:
        # Convert all parameter settings to lists
        for k, v in params.items():
            if not isinstance(v, list):
                params[k] = [v]      

        # Find the best parameter setting
        params = search_model_params(Xtrain, yTrain, method, params, paramSearchResultsPath, scoringOptiMetric)

    else:
        # Convert all parameter settings to to single values. If list, first value is taken
        for k, v in params.items():
            if isinstance(v, list):
                params[k] = v[0]

    # Predict outcome of validation and test data, print some performance metrics
    yTrueVal, yPredRegVal = validate_model(Xtrain, yTrain, method, params)
    yTrueTest, yPredRegTest = test_model(Xtrain, Xtest, yTrain, yTest, method, params)

    params['scoringOptiMetric'] = scoringOptiMetric
    return yTrueTest, yPredRegTest, yTrueVal, yPredRegVal, params

def search_model_params(Xtrain, yTrain, method, params, paramSearchResultsPath, scoringOptiMetric):
    """
    ACTION: 
        Computes the best parameter setting by searching the grid of parameter settings specified by the params-dictionary. 
    INPUTS: 
        Xtrain: DataFrame with training features
        yTrain: DataFrame with training labels
        method: machine learning algorithm to use, eg. 'RFreg' (random forest regression), 'RFclass' (random forest classifier), 'LogReg' (logistic regression)
        params: parameter settings for the selected method (a dictionary, values must be lists)
                For RFreg: n_estimators, max_features, max_depth
                For RFclass: n_estimators, max_features, max_depth
                For LogReg: penalty, solver, C, max_iter
        paramSearchResultsPath: path to csv-file that will be created, containing results from the parameter optimization
        scoringOptiMetric: metric to optimize over the given set of parameters
    OUTPUT:
        A dictionary with the best parameter setting
    """

    # Construct the ml model
    if method == 'RFreg':
        model = RandomForestRegressor(random_state=0)
    elif method == 'RFclass':
        model = RandomForestClassifier(random_state=0)
    elif method == 'LogReg':
        model = LogisticRegression(random_state=0)             
    else:
        print(f'Method "{method}" is not implemented in ml_prediction.py')
        return

    # Create model and do grid search
    modelSearch = GridSearchCV(model, params, scoring=scoringOptiMetric, cv = min(5, int(len(yTrain)/2)))
    modelSearch.fit(Xtrain.values, yTrain.values.ravel())

    # Create a csv-file with the results of the model-parameter-search
    df = pd.DataFrame(modelSearch.cv_results_)
    df.to_csv(paramSearchResultsPath, sep=';')

    # Return the best parameter setting
    return modelSearch.best_params_

def validate_model(Xtrain, yTrain, method, params):
    """
    ACTION: 
        Run cross-validation on the training data, prints some validation results, and return true and predicted labels
    INPUTS: 
        Xtrain: DataFrame with training features
        yTrain: DataFrame with training labels
        method: machine learning algorithm to use, eg. 'RFreg' (random forest regression), 'RFclass' (random forest classifier)
        params: parameter settings for the selected method (a dictionary, values cannot be lists)
    OUTPUTS: 
        yTrue: Numpy-array with true outcome values
        yPredReg: Numpy-array with predicted regression outcome values
    """

    # Construct the ml model
    if method == 'RFreg':
        model = RandomForestRegressor(**params, random_state=0)
    elif method == 'RFclass':
        model = RandomForestClassifier(**params, random_state=0)
    elif method == 'LogReg':
        model = LogisticRegression(**params, random_state=0)
        Xtrain=(Xtrain-Xtrain.mean())/Xtrain.std() # Standardize data        
    else:
        print(f'Method "{method}" is not implemented in ml_prediction.py')
        return

    # Create k-fold object
    nSplits = 5
    kf = KFold(n_splits=nSplits, shuffle=True, random_state=15)
    
    # Init vectors for prediction values
    yPredReg = np.zeros(len(yTrain.index))
    yTrue = np.zeros(len(yTrain.index))
    
    for trainIndex, testIndex in kf.split(Xtrain):

        # Split into train and test data
        X1 = Xtrain.values[trainIndex]
        y1 = yTrain.values[trainIndex]
        X2 = Xtrain.values[testIndex]
        y2 = yTrain.values[testIndex]    

        # Train model and make prediction on the test data
        model.fit(X1, y1.ravel())
        yPredReg[testIndex] = model.predict(X2)
        yTrue[testIndex] = y2.ravel()

    # Print performance metrics, return true outcome and predicted values
    print_metrics(yTrue, yPredReg)
    return yTrue, yPredReg

def test_model(Xtrain, Xtest, yTrain, yTest, method, params):
    """
    ACTION: 
        Train a model on the training data with given parameters and test it on the test data. 
        Some performance metrics will be printed, and true and predicted labels are returned. 
    INPUTS: 
        Xtrain: DataFrame with training features
        Xtest: DataFrame with test features
        yTrain: DataFrame with training labels
        yTest: DataFrame with test labels
        method: machine learning algorithm to use, eg. 'RFreg' (random forest regression), 'RFclass' (random forest classifier), 'LogReg' (logistic regression)
        params: parameter settings for the selected method (a dictionary, values cannot be lists)
                For RFreg: n_estimators, max_features, max_depth
                For RFclass: n_estimators, max_features, max_depth
                For LogReg: penalty, solver, C, max_iter
    OUTPUTS: 
        yTrue: Numpy-array with true outcome values
        yPredReg: Numpy-array with predicted regression outcome values
    """
    
    # Construct the ml model
    if method == 'RFreg':
        model = RandomForestRegressor(**params, random_state=0)
    elif method == 'RFclass':
        model = RandomForestClassifier(**params, random_state=0)
    elif method == 'LogReg':
        model = LogisticRegression(**params, random_state=0)
        # Standardize data: 
        Xtrain=(Xtrain-Xtrain.mean())/Xtrain.std()        
        Xtest=(Xtest-Xtrain.mean())/Xtrain.std()             
    else:
        print(f'Method "{method}" is not implemented in ml_prediction.py')
        return
    
    # Train model and make prediction on the test data
    model.fit(Xtrain.values, yTrain.values.ravel())
    yPredReg = model.predict(Xtest)
    yTrue = yTest.values.ravel()

    # Print performance metrics, return true outcome and predicted values
    print_metrics(yTrue, yPredReg)
    return yTrue, yPredReg


def print_metrics(yTrue, yPredReg):
    """
    ACTION: 
        Print some performance metrics
    INPUT: 
        yTrue: True output values as list or numpy array
        yPredReg: Predicted regressional output values as list or numpy array (list of int if classification)
    """

    # Round values to get predicted class
    yPredClass = np.round(yPredReg).astype(int)
    
    print('')
    print('Accuracy:          ', metrics.accuracy_score(yTrue, yPredClass))
    print('Precicion (micro): ', metrics.precision_score(yTrue, yPredClass, average='micro', zero_division=0))
    print('Recall (micro):    ', metrics.recall_score(yTrue, yPredClass, average='micro', zero_division=0))
    print('Precicion (macro): ', metrics.precision_score(yTrue, yPredClass, average='macro', zero_division=0))
    print('Recall (macro):    ', metrics.recall_score(yTrue, yPredClass, average='macro', zero_division=0))
    
def write_results_to_csv(predResultsPath, selectionFeaturesPath, FSmethod, FSparams, selectedFeatures, MLmethod, MLparams, yTrueTest, yPredRegTest, yTrueVal, yPredRegVal):
    """
    ACTION: 
        Writes result metrics together with method information to a csv-file
    INPUTS: 
        predResultsPath: Path to the csv-file where to write the results
        selectionFeaturesPath: Path to the feature selection file that was used 
        FSmethod: Feature selection method
        FSparams: Feature selection parameters
        selectedFeatures: Selected features
        MLmethod: Prediction model
        MLparams: Prediction model parameters
        yTrueTest: Numpy-array with true outcome values of the test data
        yPredRegTest: Numpy-array with predicted regression outcome values of the test data
        yTrueVal: Numpy-array with true outcome values of the validation data
        yPredRegVal: Numpy-array with predicted regression outcome values of the validation data
    """

    # Round values to get predicted class
    yPredClassTest = np.round(yPredRegTest).astype(int)
    yPredClassVal = np.round(yPredRegVal).astype(int)

    # Creates a dictionary with information about methods and parameter settings
    resultsDict = {'selectionFeaturesPath' : selectionFeaturesPath,
                    'FSmethod': FSmethod,
                    'FSparams' : FSparams,
                    'selectedFeatures' : selectedFeatures,
                    'MLmethod' : MLmethod,
                    'MLparams' : MLparams,
                    'yTrueTest' : yTrueTest.tolist(),
                    'yPredRegTest' : yPredRegTest.tolist(),
                    'yPredClassTest' : yPredClassTest.tolist(),
                    'yTrueVal' : yTrueVal.tolist(),
                    'yPredRegVal' : yPredRegVal.tolist(),
                    'yPredClassVal' : yPredClassVal.tolist()}

    # Add result metrics to dictionary
    resultsDict['accuracyTest'] = metrics.accuracy_score(yTrueTest, yPredClassTest)
    resultsDict['precisionMicroTest'] = metrics.precision_score(yTrueTest, yPredClassTest, average='micro', zero_division=0)
    resultsDict['precisionMacroTest'] = metrics.precision_score(yTrueTest, yPredClassTest, average='macro', zero_division=0)
    resultsDict['recallMicroTest'] = metrics.recall_score(yTrueTest, yPredClassTest, average='micro', zero_division=0)
    resultsDict['recallMacroTest'] = metrics.recall_score(yTrueTest, yPredClassTest, average='macro', zero_division=0)
    resultsDict['f1MicroTest'] = metrics.f1_score(yTrueTest, yPredClassTest, average='micro', zero_division=0)
    resultsDict['f1MacroTest'] = metrics.f1_score(yTrueTest, yPredClassTest, average='macro', zero_division=0)
    resultsDict['r2Test'] = metrics.r2_score(yTrueTest, yPredRegTest)
    resultsDict['rmseTest'] = np.sqrt(metrics.mean_squared_error(yTrueTest, yPredRegTest))

    resultsDict['accuracyVal'] = metrics.accuracy_score(yTrueVal, yPredClassVal)
    resultsDict['precisionMicroVal'] = metrics.precision_score(yTrueVal, yPredClassVal, average='micro', zero_division=0)
    resultsDict['precisionMacroVal'] = metrics.precision_score(yTrueVal, yPredClassVal, average='macro', zero_division=0)
    resultsDict['recallMicroVal'] = metrics.recall_score(yTrueVal, yPredClassVal, average='micro', zero_division=0)
    resultsDict['recallMacroVal'] = metrics.recall_score(yTrueVal, yPredClassVal, average='macro', zero_division=0)
    resultsDict['f1MicroVal'] = metrics.f1_score(yTrueVal, yPredClassVal, average='micro', zero_division=0)
    resultsDict['f1MacroVal'] = metrics.f1_score(yTrueVal, yPredClassVal, average='macro', zero_division=0)
    resultsDict['r2Val'] = metrics.r2_score(yTrueVal, yPredRegVal)
    resultsDict['rmseVal'] = np.sqrt(metrics.mean_squared_error(yTrueVal, yPredRegVal))

    # List all the column names to use in file
    header = list(resultsDict.keys())

    # If the file exists we append the new content
    if os.path.isfile(predResultsPath):
        with open(predResultsPath, 'a+', newline='') as predResultsFile:
            writer = csv.DictWriter(predResultsFile, fieldnames=header, delimiter = ';')
            writer.writerow(resultsDict)

    # If the file does not exists we create the header and then add the content
    else: 
        with open(predResultsPath, 'w', newline='') as predResultsFile:
            writer = csv.DictWriter(predResultsFile, fieldnames=header, delimiter = ';')
            writer.writeheader()
            writer.writerow(resultsDict)
